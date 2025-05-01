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

P4LACPP = "p4lacpp"  # Path to the p4lacpp executable (in $PATH)

def debug_print(msg):
    # Uncomment the next line to enable debug printing
    #print(f"DEBUG: {msg}")
    pass
def info_print(msg):
    #print(f"INFO: {msg}")
    pass
### Table Graph Processing BEGIN
# dependancy bits
DEPENDENCY_ATTRS = {
    "NONE": 1,
    "CONTROL_ACTION": (1 << 1),
    "CONTROL_COND_TRUE": (1 << 2),
    "CONTROL_COND_FALSE": (1 << 3),
    "CONTROL_TABLE_HIT": (1 << 4),
    "CONTROL_TABLE_MISS": (1 << 5),
    "CONTROL_DEFAULT_NEXT_TABLE": (1 << 6),
    "IXBAR_READ": (1 << 7),
    "ACTION_READ": (1 << 8),
    "OUTPUT": (1 << 9),
    "REDUCTION_OR_READ": (1 << 10),
    "REDUCTION_OR_OUTPUT": (1 << 11),
    "CONT_CONFLICT": (1 << 12),
    "ANTI_EXIT": (1 << 13),
    "ANTI_TABLE_READ": (1 << 14),
    "ANTI_ACTION_READ": (1 << 15),
    "ANTI_NEXT_TABLE_DATA": (1 << 16),
    "ANTI_NEXT_TABLE_CONTROL": (1 << 17),
    "ANTI_NEXT_TABLE_METADATA": (1 << 18),
    "CONTROL_EXIT": (1 << 19),
    "CONCURRENT": 0
}

def dependency_to_bitvector(dep_str):
    """Given a space-separated dependency string, return a 20-bit binary list."""
    bitmask = 0
    for token in dep_str.split():
        if token in DEPENDENCY_ATTRS:
            bitmask |= DEPENDENCY_ATTRS[token]
        else:
            raise ValueError(f"Unknown dependency attribute: {token}")
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
            table_name = clean_node_name(table_info)
            dep_labels = [c for c in prefix.replace('-', '').strip().replace(' ', '').strip()]
            dependency_matrix.append(dep_labels)
            table_list.append(table_name)

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
        edge_attr.append(bin(list(data['labels'])[0])[2:])  # Count the number of bits set to 1

    gnn_data = {
        "nodes": node_names,
        "edge_index": edge_index,
        "edge_attr": edge_attr
    }

    return gnn_data

### Table Graph Processing END

### JSON Processing

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
                debug_print(f"Error in {json_file}: 'mau_stages' is not a list.")
                return -1
    except (FileNotFoundError, json.JSONDecodeError) as e:
        debug_print(f"Error reading {json_file}: {e}")
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
                debug_print(f"Error in {json_file}: 'latency' is not a list.")
                return -1
    except (FileNotFoundError, json.JSONDecodeError) as e:
        debug_print(f"Error reading {json_file}: {e}")
        return -1

def load_all_node_attrs_and_labels(directory):
    all_node_attrs = []
    all_labels = []

    file_paths = []
    for filename in os.listdir(directory):
        if filename.endswith(".json"):
            path = os.path.join(directory, filename)
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
    for path in tqdm(file_paths, desc="Normalizing"):
        with open(path, "r") as f:
            data = json.load(f)

        if "node_attr" in data:
            x = np.array(data["node_attr"], dtype=np.float32)
            data["node_attr_normalized"] = ((x - node_mean) / node_std).tolist()

        if "y" in data and isinstance(data["y"], list):
            y = np.array(data["y"], dtype=np.float32)
            data["y_normalized"] = ((y - label_mean) / label_std).tolist()

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

def plot_distribution(data, prefix):
    num_features = data.shape[1]
    for i in range(num_features):
        plt.hist(data[:, i], bins=20, alpha=0.7)
        plt.title(f"Distribution of {prefix}_{i}")
        plt.xlabel(f"{prefix}_{i}")
        plt.ylabel("Frequency")
        plt.grid(True)
        plt.savefig(f"{prefix}_{i}_distribution.png")
        plt.close()

def normalize_node_attr_and_label(directory):
    file_paths, all_node_attrs, all_labels = load_all_node_attrs_and_labels(directory)

    # Normalize
    norm_node_attr, node_mean, node_std = z_score(all_node_attrs)
    norm_labels, label_mean, label_std = z_score(all_labels)

    # Plot
    plot_distribution(all_node_attrs, "node_attr")
    plot_distribution(all_labels, "y")

    # # Update files
    normalize_and_update_files(file_paths, node_mean, node_std, label_mean, label_std)

    info_print("All files updated with normalized features.")


### JSON Processing END

### Node feature extraction
def extract_table_vector(table, actions_dict):
    size = table.get("size", 0)
    actions = table.get("actions", [])
    matches = table.get("matches", [])

    op_num_sum = 0
    for act in actions:
        act_meta = actions_dict.get(act, {"op_num": 0})
        op_num_sum += act_meta.get("op_num", 0)

    lpm_count = 0
    exact_count = 0
    ternary_count = 0

    for match in matches:
        match_type = match[0]
        if match_type == "lpm":
            lpm_count += len(match[1])
        elif match_type == "exact":
            exact_count += len(match[1])
        elif match_type == "ternary":
            ternary_count += len(match[1])
    # unknown table
    unknown = 0
    feature_vector = [
        size,
        op_num_sum,
        lpm_count,
        exact_count,
        ternary_count,
        unknown
    ]
    debug_print(f"Table: {table}, Feature vector: {feature_vector}")
    return feature_vector

def extract_node_features(p4_file,gnn_data):
    node_names = gnn_data["nodes"]
    output_file = "node_features.json"
    with open(output_file, 'w') as file:
        try:
            subprocess.run(
                [P4LACPP, p4_file,"-f",file.name],
                stderr=subprocess.PIPE,
                check=True
            )
        except Exception as e:
            debug_print(f"Error running p4lacpp on {p4_file}: {e}")
            return
    with open(output_file, 'r') as file:
        data = json.load(file)
        # TODO: egress
        ingress = data.get("ingress", {})
        tables = ingress.get("tables", {})
        actions = ingress.get("actions", {})
        node_attr = []

        for node in node_names:
            if node in tables:
                table = tables[node]
                feature_vector = extract_table_vector(table, actions)
                node_attr.append(feature_vector)
            elif "tbl_" in node:
                debug_print(f"Node {node} is an action table.")
                feature_vector = [0, 0, 0, 0, 0, 1]
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
                # set unknown table to 1
                node_attr.append([0, 0, 0, 0, 0, 1])
        gnn_data["node_attr"] = node_attr
    return gnn_data
    


def process_p4_folders(root_dir):
    """
    Recursively finds P4 program folders and processes their JSON files.
    """
    for root, _, files in os.walk(root_dir):
        if any(file.endswith("smith.p4") for file in files):
            resource_file = os.path.join(root,"smith.tofino/pipe", "logs/resources.json")
            metrics_file = os.path.join(root, "smith.tofino/pipe", "metrics.json")
            dependancy_file = os.path.join(root, "smith.tofino/pipe/logs", "table_dependency_summary.log")
            mau_len = 0
            lat = 0
            debug_print(f"Processing P4 folder: {root}")
            
            if os.path.exists(resource_file):
                size = process_resource_json(resource_file)
                if size != -1:
                    info_print(f"Size of 'mau_stages' in {resource_file}: {size}")
                    mau_len = size
            else:
                debug_print(f"Missing resource file: {resource_file}")
            
            if os.path.exists(metrics_file):
                [latencies, sram, tcam] = process_metrics_json(metrics_file)
                if latencies != -1:
                    for latency in latencies:
                        info_print(f"gress: {latency['gress']}, cycles: {latency['cycles']}")
                        lat += latency['cycles']
            else:
                debug_print(f"Missing metrics file: {metrics_file}")


            if os.path.exists(dependancy_file):
                gnn_data = process_table_dependency_summary(dependancy_file)
                debug_print(f"Processed table dependency summary: {gnn_data}")
            else:
                debug_print(f"Missing dependency file: {dependancy_file}")

            gnn_data = extract_node_features(os.path.join(root, "opt.p4"),gnn_data)

            # write to a file with the same name as the folder
            output_file = os.path.join(root, "data.json")
            gnn_data["y"] = [mau_len, lat,sram, tcam]
            save_to_json(gnn_data, output_file)             

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
    args = parser.parse_args()
    
    process_p4_folders(args.directory)
    copy_p4_programs_to_dataset(args.directory)
    normalize_node_attr_and_label(args.output)
# exp python3 ./code_gen_data_collect/parse_performance.py -d . 
if __name__ == "__main__":
    main()
