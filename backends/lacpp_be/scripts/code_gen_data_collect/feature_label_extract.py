import json
import argparse
import os
import shutil
import re
import subprocess
import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed

NODE_ATTRIBUTES = {0: "size", 1: "op_num_sum", 
                   2: "lpm_count", 3: "lpm_size",
                   4: "exact_count", 5: "exact_size",
                   6: "ternary_count", 7: "ternary_size",
                   8: "max_act_param_size",
                   9: "unknown"}
# note: latency is only that of ingress, we don't consider egree rn
LABEL_ATTRIBUTES = {0: "mau_len", 1: "latency", 2: "sram", 3: "tcam"}

P4LACPP = "p4lacpp"  # Path to the p4lacpp executable (in $PATH)

def debug_print(msg):
    #print(f"DEBUG: {msg}")
    pass
def info_print(msg):
    #print(f"INFO: {msg}")
    pass

def process_table_name(table_name):
    # tables names are changed for the convinience of the comipler. 
    # Here are all the rules:
    # 1. append _\d, like table_0, table_1, etc.
    # 2. append $action, like 
    #    table$action, table_0$action, etc.
    # 3. prefixes for control blocks, like ingress.table
    # We need to remove these suffixes to get the original table name.
    # note: @name pragma overwrites the name, but smith uses it that fits these rules.
    table_name = table_name.split('.')[-1] 
    # note: this is in resources.json, but now we use power.json for collecting sram
    #  which does not make $action explicit, so skip..
    # if table_name.endswith('$action'):
    #     table_name = table_name[:-len('$action')]
    # This is bad, but should works? I never saw more than _1..
    if table_name.endswith('_0'):
        table_name = table_name[:-len('_0')]
    if table_name.endswith('_1'):
        table_name = table_name[:-len('_1')]
    return table_name

### Table Graph Processing BEGIN
# dependancy bits
DEPENDENCY_ATTRS = {
    # "NONE": 1, These two do not show up
    # "CONCURRENT": 0
    "CONTROL_ACTION": 1,
    "CONTROL_COND_TRUE": 1,
    "CONTROL_COND_FALSE": 1,
    "CONTROL_TABLE_HIT": 1,
    "CONTROL_TABLE_MISS": 1,
    "CONTROL_DEFAULT_NEXT_TABLE": 1,
    "CONTROL_EXIT": 1,

    "ANTI_EXIT": (1 << 1),
    "ANTI_TABLE_READ": (1 << 1),
    "ANTI_ACTION_READ": (1 << 1),
    "ANTI_NEXT_TABLE_DATA": (1 << 1),
    "ANTI_NEXT_TABLE_CONTROL": (1 << 1),
    "ANTI_NEXT_TABLE_METADATA": (1 << 1),

    "IXBAR_READ": (1 << 2),
    "ACTION_READ": (1 << 2),
    "OUTPUT": (1 << 2),

    # ignore these 3, they are rare
    # "REDUCTION_OR_READ": (1 << 10),
    # "REDUCTION_OR_OUTPUT": (1 << 11),
    # "CONT_CONFLICT": (1 << 12),
}

def dependency_to_bitvector(dep_str):
    """Given a space-separated dependency string, return a 3-bit binary list."""
    bitmask = 0
    for token in dep_str.split():
        if token in DEPENDENCY_ATTRS:
            bitmask |= DEPENDENCY_ATTRS[token]
        else:
            debug_print(f"Unencoded dependency token: {token}")
    return bitmask

def clean_node_name(raw_name):
    # Remove everything in parentheses
    return re.sub(r"\(.*?\)", "", raw_name).strip()
def save_to_json(obj, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)

def process_table_dependency_summary(filepath):
    graph = nx.DiGraph()
    table_list = []
    dependency_matrix = []
    dependency_char_map = {}

    with open(filepath, 'r') as f:
        lines = f.readlines()

    parsing_dependencies = False

    for line in lines:
        line = line.strip()

        if line.startswith("#dependencies"):
            parsing_dependencies = True
            continue

        if parsing_dependencies:
            if not line or line.startswith("#") or ":" not in line:
                continue
            # A : IXBAR_READ OUTPUT ...
            key, val = line.split(":", 1)
            dependency_char_map[key.strip()] = val.strip()
            continue

        if line.startswith("#stage") or line.startswith("#pipeline") or line.startswith("***") or line.startswith("#") or not line:
            continue

        if "^" in line:
            parts = line.split("^")
            prefix = parts[0].strip()
            table_info = parts[1].strip().split(":")[0].strip().split("-")[-1].strip()
            table_name = process_table_name(clean_node_name(table_info))
            dep_labels = [c for c in prefix.strip().replace(' ', '').strip()]
            dependency_matrix.append(dep_labels)
            table_list.append(table_name)
            graph.add_node(table_name, label=table_name)
    # Build the graph
    for i, deps in enumerate(dependency_matrix):
        for j, label in enumerate(deps):
            if label.isalpha():
                src = table_list[j]
                dst = table_list[i]
                deps_vec = dependency_to_bitvector(dependency_char_map[label])
                graph.add_edge(src, dst, labels={deps_vec})

    # Convert to GNN format
    node_names = list(graph.nodes())
    node_to_id = {name: idx for idx, name in enumerate(node_names)}
    
    edge_index = [[], []]
    edge_attr = []

    for src, dst, data in graph.edges(data=True):
        edge_index[0].append(node_to_id[src])
        edge_index[1].append(node_to_id[dst])
        edge_attr.append(bin(list(data['labels'])[0])[2:]) 

    gnn_data = {
        "nodes": node_names,
        "edge_index": edge_index,
        "edge_attr": edge_attr
    }

    return gnn_data

### Table Graph Processing END

### JSON Processing

# get the memo usage for each table
def process_power_json(power_json_file, node_list):
    with open(power_json_file, 'r') as f:
        data = json.load(f)
    
    sram_per_table = {}
    tcam_per_table = {}
    for table in data['tables']:
        tbl_name = process_table_name(table['name'])
        mau_stages = table['stages']
        for stage in mau_stages:
            memos = stage['memories']
            for m in memos:
                num = m['num_memories']
                if m['memory_type'] == 'sram':
                    if tbl_name not in sram_per_table:
                        sram_per_table[tbl_name] = num
                    else:
                        sram_per_table[tbl_name] += num
                elif m['memory_type'] == 'tcam':
                    if tbl_name not in tcam_per_table:
                        tcam_per_table[tbl_name] = num
                    else:
                        tcam_per_table[tbl_name] += num
                else:
                    print(f"Unknown memory type {m['memory_type']} for table {tbl_name}")
    debug_print(f"SRAM per table: {sram_per_table}")
    debug_print(f"TCAM per table: {tcam_per_table}")
    # order it based on the node list
    sram_list = []
    tcam_list = []
    for node in node_list:
        tbl_name = node
        if tbl_name in sram_per_table:
            debug_print(f"Table {tbl_name} found in SRAM data: {sram_per_table[tbl_name]}")
            sram_list.append(sram_per_table[tbl_name])
        else:
            # Hao: seems any table will have at least one sram used, make sure its the case!
            debug_print(f"Table {tbl_name} not found in SRAM data, setting to 1.")
            sram_list.append(1)
        if tbl_name in tcam_per_table:
            tcam_list.append(tcam_per_table[tbl_name])
        else:
            debug_print(f"Table {tbl_name} not found in TCAM data, setting to 0.")
            tcam_list.append(0)
    return sram_list, tcam_list

# currently we only want mau usage from the resources.json file
def process_resource_json(json_file):
    """
    Reads a JSON file and fetches the size of the list at 'resources' -> 'mau' -> 'mau_stages'.
    """
    try:
        with open(json_file, 'r') as file:
            data = json.load(file)
            
            mau_stages = data.get("resources", {}).get("mau", {}).get("mau_stages", [])
            
            if isinstance(mau_stages, list):
                return len(mau_stages)
            else:
                print(f"Error in {json_file}: 'mau_stages' is not a list.")
                return -1
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {json_file}: {e}")
        return -1
    except Exception as e:
        print(f"Unexpected error in {json_file}: {e}")
        return -1

def process_metrics_json(json_file):
    try:
        with open(json_file, 'r') as file:
            data = json.load(file)
            
            latency = data.get("mau", {}).get("latency", None)
            sram = data.get("mau", {}).get("srams", None)
            tcam = data.get("mau", {}).get("tcams", None)
            if isinstance(latency, list):
                return [latency, sram, tcam]
            else:
                print(f"Error in {json_file}: 'latency' is not a list.")
                return -1
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {json_file}: {e}")
        return -1

def load_all_node_attrs_and_labels(directory):
    all_node_attrs = []
    all_labels = []

    file_paths = []

    for root, _, files in os.walk(directory):
        for filename in files:
            if filename.endswith(".json"):
                path = os.path.join(root, filename)
                file_paths.append(path)
                with open(path, "r") as f:
                    data = json.load(f)
                    if "node_attr" in data:
                        all_node_attrs.extend(data["node_attr"])
                    if "y" in data and isinstance(data["y"], list):
                        all_labels.extend([data["y"]])
    # print dimensions
    info_print(f"Number of node attributes: {len(all_node_attrs)}")
    info_print(f"Number of labels: {len(all_labels)}")
    return file_paths, np.array(all_node_attrs, dtype=np.float32), np.array(all_labels, dtype=np.float32)

def z_score(data):
    mean = np.mean(data, axis=0)
    std = np.std(data, axis=0)

    if np.isscalar(std):
        std = std if std != 0 else 1.0
    else:
        std[std == 0] = 1.0

    return (data - mean) / std, mean, std

def normalize_and_update_files(file_paths, node_mean, node_std, label_mean, label_std):

    for i, path in enumerate(tqdm(file_paths, desc="Normalizing")):
        with open(path, "r") as f:
            data = json.load(f)

        if "node_attr" in data:
            x = np.array(data["node_attr"], dtype=np.float32)
            data["node_attr_normalized"] = ((x - node_mean) / node_std).tolist()
            for i, e in enumerate(x):
                if e[-1] == 1:
                    # this is an unknown table, we don't normalize this field..
                    data["node_attr_normalized"][i][-1] = 1

        if "y" in data and isinstance(data["y"], list):
            y = np.array(data["y"], dtype=np.float32)
            data["y_normalized"] = ((y - label_mean) / label_std).tolist()

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

def plot_distribution(data, prefix):
    num_features = data.shape[1]
    for i in range(num_features):
        plt.hist(data[:, i], bins=20, alpha=0.7)
        if prefix == "node_attr":
            name = f"{prefix}_{NODE_ATTRIBUTES[i]}"
        else:
            name = f"{prefix}_{LABEL_ATTRIBUTES[i]}"
        plt.title(f"Distribution of {name}")
        plt.xlabel(f"{name}")
        plt.ylabel("Frequency")
        plt.grid(True)
        os.makedirs("dist_figs", exist_ok=True)
        if prefix == "node_attr":
            plt.savefig(f"dist_figs/{name}_distribution.png")
        else:
            plt.savefig(f"dist_figs/{name}_distribution.png")
        plt.close()

def normalize_node_attr_and_label(directory):
    file_paths, all_node_attrs, all_labels = load_all_node_attrs_and_labels(directory)

    # Normalize
    norm_node_attr, node_mean, node_std = z_score(all_node_attrs)
    norm_labels, label_mean, label_std = z_score(all_labels)
    # store the means and stds
    with open("means_stds.json", "w") as f:
        json.dump({
            "node_mean": node_mean.tolist(),
            "node_std": node_std.tolist(),
            "label_mean": label_mean.tolist(),
            "label_std": label_std.tolist()
        }, f, indent=2)
    # Plot
    plot_distribution(all_node_attrs, "node_attr")
    plot_distribution(all_labels, "y")

    # # # Update files
    normalize_and_update_files(file_paths, node_mean, node_std, label_mean, label_std)

    info_print("All files updated with normalized features.")


### JSON Processing END

### Node feature extraction
def extract_table_vector(table, actions_dict):
    entry_size = table.get("size", 0)
    actions = table.get("actions", [])
    matches = table.get("matches", [])
    max_act_param_size = 0

    op_num_sum = 0
    for act in actions:
        act_meta = actions_dict.get(act)
        op_num_sum += act_meta.get("op_num")
        max_act_param_size = max(max_act_param_size, act_meta.get("params_size", 0))

    lpm_count = 0
    lpm_size = 0
    exact_count = 0
    exact_size = 0
    ternary_count = 0
    ternary_size = 0

    for match in matches:
        match_type = match[0]
        keys = match[1]
        size = 0
        for e in keys:
            size+=e[1]
        if match_type == "lpm":
            lpm_count += len(keys)
            lpm_size = size
        elif match_type == "exact":
            exact_count += len(keys)
            exact_size = size
        elif match_type == "ternary":
            ternary_count += len(keys)
            ternary_size = size
    # unknown table
    unknown = 0
    feature_vector = [
        entry_size,
        op_num_sum,
        lpm_count,
        lpm_size,
        exact_count,
        exact_size,
        ternary_count,
        ternary_size,
        max_act_param_size,
        unknown
    ]
    debug_print(f"Table: {table}, Feature vector: {feature_vector}")
    return feature_vector

def extract_node_features(p4_file,gnn_data):
    # nodes extracted from table_dep_summary.log
    node_names = gnn_data["nodes"]
    output_file = os.path.join(os.path.dirname(p4_file), "node_features.json")
    with open(output_file, 'w') as file:
        try:
            subprocess.run(
                [P4LACPP, p4_file,"-f",file.name],
                stderr=subprocess.PIPE,
                check=True
            )
        except Exception as e:
            print(f"Error running p4lacpp on {p4_file}: {e}")
            return
    with open(output_file, 'r') as file:
        data = json.load(file)
        # TODO: egress
        ingress = data.get("ingress", {})
        tables = ingress.get("tables", {})
        tables = {process_table_name(k): v for k, v in tables.items()}

        actions = ingress.get("actions", {})
        node_attr = []

        for node in node_names:
            if node in tables:
                table = tables[node]
                feature_vector = extract_table_vector(table, actions)
                node_attr.append(feature_vector)
            elif "tbl_" in node:
                # Hao: I later limited this case, no action in the apply (i think so..)
                debug_print(f"Node {node} is an action table.")
                feature_vector = list([0] * len(NODE_ATTRIBUTES))
                feature_vector[-1] = 1  # set unknown table to 1
                for action in actions:
                    # check if the string with tbl_ removed is in the action name
                    if node[4:] in action:
                        table = {"size": 0, "actions": [action], "matches": []}
                        feature_vector = extract_table_vector(table, actions)
                        debug_print(f"Node {node} is an action table with action {action}.")
                        debug_print(f"Feature vector: {feature_vector}")
                        break
                node_attr.append(feature_vector)
            else:
                #like $precompute tables
                debug_print(f"Node {node} is not a table or action table.")
                feature_vector = list([0] * len(NODE_ATTRIBUTES))
                feature_vector[-1] = 1  # set unknown table to 1
                node_attr.append(feature_vector)
        gnn_data["node_attr"] = node_attr
    return gnn_data
    
def process_single_p4_folder(root):
    """
    Processes a single P4 folder.
    """
    try:
        resource_file = os.path.join(root, "smith.tofino/pipe", "logs/resources.json")
        metrics_file = os.path.join(root, "smith.tofino/pipe", "metrics.json")
        dependency_file = os.path.join(root, "smith.tofino/pipe/logs", "table_dependency_summary.log")
        power_file = os.path.join(root, "smith.tofino/pipe/logs", "power.json")

        mau_len = 0
        lat = 0
        sram = 0
        tcam = 0
        gnn_data = {}

        debug_print(f"Processing P4 folder: {root}")

        if os.path.exists(resource_file):
            size = process_resource_json(resource_file)
            if size != -1:
                info_print(f"Size of 'mau_stages' in {resource_file}: {size}")
                mau_len = size
        else:
            raise FileNotFoundError(f"Resource file not found: {resource_file}")

        if os.path.exists(metrics_file):
            [latencies, sram, tcam] = process_metrics_json(metrics_file)
            if latencies != -1:
                for latency in latencies:
                    if latency['gress'] == "ingress":
                        info_print(f"gress: {latency['gress']}, cycles: {latency['cycles']}")
                        lat += latency['cycles']
        else:
            raise FileNotFoundError(f"Metrics file not found: {metrics_file}")

        if os.path.exists(dependency_file):
            gnn_data = process_table_dependency_summary(dependency_file)
            debug_print(f"Processed table dependency summary: {gnn_data}")
        else:
            raise FileNotFoundError(f"Dependency file not found: {dependency_file}")
        
        if os.path.exists(power_file):
            sram_list, tcam_list = process_power_json(power_file, gnn_data["nodes"])
            debug_print(f"Processed power JSON: SRAM {sram_list}, TCAM {tcam_list}")
        else:
            debug_print(f"Missing power file: {power_file}")
            raise FileNotFoundError(f"Power file not found: {power_file}")

        gnn_data = extract_node_features(os.path.join(root, "opt.p4"), gnn_data)
        gnn_data["y"] = [mau_len, lat, sram, tcam]
        # add per table memo to gnn_data, also labels
        gnn_data["sram"] = sram_list
        gnn_data["tcam"] = tcam_list
        output_file = os.path.join(root, "data.json")
        save_to_json(gnn_data, output_file)

        return (root, "success")

    except Exception as e:
        return (root, f"error: {e}")

def process_p4_folders(root_dir, num_workers=4):
    """
    Recursively finds P4 program folders and processes their JSON files using multiprocessing.
    """
    p4_dirs = []

    for root, _, files in os.walk(root_dir):
        if any(file.endswith("smith.p4") for file in files):
            p4_dirs.append(root)
    process_bar = tqdm(total=len(p4_dirs), desc="Processing P4 folders", unit="folder")
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_single_p4_folder, folder): folder for folder in p4_dirs}
        for future in as_completed(futures):
            process_bar.update(1)
            folder = futures[future]
            result = future.result()
            if result[1] == "success":
                info_print(f"Successfully processed {folder}")
            else:   
                raise Exception(result[1])


def copy_p4_programs_to_dataset(root_dir):
    """
    Recursively finds P4 programs and copies them along with 'data.json' to the 'dataset' folder.
    """
    dataset_dir = "dataset"
    os.makedirs(dataset_dir, exist_ok=True)
    
    for root, _, files in os.walk(root_dir):
        # skip dataset folder
        if 'dataset' in root.split(os.sep):
            continue
        if any(file.endswith("opt.p4") for file in files):
            folder_name = os.path.basename(root)
            os.makedirs(dataset_dir, exist_ok=True)
            
            for file in files:
                if file == "data.json": #or file == "node_features.json" or file.endswith("opt.p4"):
                    src_path = os.path.join(root, file)
                    # copy to a file with the same name as the source folder
                    dst_path = os.path.join(dataset_dir,folder_name+".json")
                    shutil.copy2(src_path, dst_path)
                    debug_print(f"Copied {src_path} to {dst_path}")


def main():
    parser = argparse.ArgumentParser(description="Find P4 programs recursively and parse their JSON files for perf. Move them to dataset folder.")
    parser.add_argument("-d", "--directory", type=str, required=True, help="Root directory to search for P4 programs.")
    parser.add_argument("-o", "--output", type=str, default="dataset", help="Output directory for the dataset.")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of worker processes.")
    args = parser.parse_args()
    
    process_p4_folders(args.directory, args.workers)
    copy_p4_programs_to_dataset(args.directory)
    normalize_node_attr_and_label(args.output)
# exp python3 ./code_gen_data_collect/parse_performance.py -d . 
if __name__ == "__main__":
    main()
