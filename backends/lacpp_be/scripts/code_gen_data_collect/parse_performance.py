import json
import argparse
import os
import shutil
def get_mau_stages_size(json_file):
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

def get_latency(json_file):
    """
    Reads a JSON file and fetches the latency from the 'mau' -> 'latency' field.
    """
    try:
        with open(json_file, 'r') as file:
            data = json.load(file)
            
            latency = data.get("mau", {}).get("latency", None)
            
            if isinstance(latency, list):
                return latency
            else:
                print(f"Error in {json_file}: 'latency' is not a list.")
                return -1
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {json_file}: {e}")
        return -1

def process_p4_folders(root_dir):
    """
    Recursively finds P4 program folders and processes their JSON files.
    """
    for root, _, files in os.walk(root_dir):
        if any(file.endswith("opt.p4") for file in files):
            resource_file = os.path.join(root,"smith.tofino/pipe", "logs/resources.json")
            metrics_file = os.path.join(root, "smith.tofino/pipe", "metrics.json")
            mau_len = 0
            lat = 0
            print(f"Processing P4 folder: {root}")
            
            if os.path.exists(resource_file):
                size = get_mau_stages_size(resource_file)
                if size != -1:
                    print(f"Size of 'mau_stages' in {resource_file}: {size}")
                    mau_len = size
            else:
                print(f"Missing resource file: {resource_file}")
            
            if os.path.exists(metrics_file):
                latencies = get_latency(metrics_file)
                if latencies != -1:
                    for latency in latencies:
                        print(f"gress: {latency['gress']}, cycles: {latency['cycles']}")
                        lat += latency['cycles']
            else:
                print(f"Missing metrics file: {metrics_file}")
            # write to a file
            output_file = os.path.join(root, "perf.txt")
            with open(output_file, 'w') as f:
                f.write(f"{mau_len}, {lat}\n")

def copy_p4_programs_to_dataset(root_dir):
    """
    Recursively finds P4 programs and copies them along with 'perf.txt' to the 'dataset' folder.
    """
    dataset_dir = "dataset"
    os.makedirs(dataset_dir, exist_ok=True)
    
    for root, _, files in os.walk(root_dir):
        # skip dataset folder
        if 'dataset' in root.split(os.sep):
            continue
        if any(file.endswith("opt.p4") for file in files):
            folder_name = os.path.basename(root)
            target_dir = os.path.join(dataset_dir, folder_name)
            os.makedirs(target_dir, exist_ok=True)
            
            for file in files:
                if file.endswith("opt.p4") or file == "perf.txt":
                    src_path = os.path.join(root, file)
                    dst_path = os.path.join(target_dir, file)
                    shutil.copy2(src_path, dst_path)
                    print(f"Copied {src_path} to {dst_path}")
def main():
    parser = argparse.ArgumentParser(description="Find P4 programs recursively and parse their JSON files for perf. Move them to dataset folder.")
    parser.add_argument("-d", "--directory", type=str, required=True, help="Root directory to search for P4 programs.")
    args = parser.parse_args()
    
    process_p4_folders(args.directory)
    copy_p4_programs_to_dataset(args.directory)
# exp python3 ./code_gen_data_collect/parse_performance.py -d . 
if __name__ == "__main__":
    main()
