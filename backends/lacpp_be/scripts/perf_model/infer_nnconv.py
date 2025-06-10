import torch
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader as GeoDataLoader
from pathlib import Path
import json
import os
import time
import torch.nn as nn
from torch_geometric.nn import NNConv, global_mean_pool
import argparse
from train import NNConvPerformanceModel

# === Config ===
MODEL_PATH = "./4k_b32_hid32_lr5_best_model.pth"
DATASET_PATH = "./4k_dataset/part-1"
USE_GPU = True
SAVE_RESULTS = False  # Save predictions per file
NORMALIZATION_STATS = "./4k_dataset/means_stds.json"  # optional

device = torch.device("cuda" if USE_GPU and torch.cuda.is_available() else "cpu")

# === Load normalization stats ===
if os.path.exists(NORMALIZATION_STATS):
    with open(NORMALIZATION_STATS) as f:
        norm_stats = json.load(f)
        label_mean = torch.tensor(norm_stats["label_mean"])
        label_std = torch.tensor(norm_stats["label_std"])
else:
    label_mean = label_std = None


# === Load model ===
model = NNConvPerformanceModel(in_dim=6, hidden_dim=128, out_dim=4)
model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
model.to(device)
model.eval()

def edge_bits_to_tensor(edge_attr_strings):
    """
    Turn ["1001", "0110", ...]  →  [[1,0,0,1], [0,1,1,0], ...] (FloatTensor)
    """
    # The bitmap was stored in string
    # format, so we need to convert it to a list of lists of ints.
    # len(bitmap) is 3, as there are 3 kinds of dependencies we care, 
    bitmap = []
    for bits in edge_attr_strings:
        # convert to list of int
        bits = [int(b) for b in bits]
        bits = [0] * (3 - len(bits)) + bits
        bitmap.append(bits)
    

    return torch.tensor(bitmap, dtype=torch.float)

def load_graph(file_path):
    with open(file_path) as f:
            js = json.load(f)

    x          = torch.tensor(js["node_attr_normalized"],
                                    dtype=torch.float)            # [N, F]
    edge_index = torch.tensor(js["edge_index"],
                            dtype=torch.long)             # [2, E]
    edge_attr  = edge_bits_to_tensor(js["edge_attr"])  # [E, B]
    y          = torch.tensor(js["y"],
                            dtype=torch.float).unsqueeze(0)
    return Data(x=x, edge_index=edge_index, edge_attr=edge_attr, y=y)

def run_test_set():
    # === Inference on all graphs in folder ===
    results = {}
    maes = []
    mapes = []
    # recursively find all .json files in the dataset path
    if not os.path.exists(DATASET_PATH):
        print(f"Dataset path {DATASET_PATH} does not exist.")
        return
    
    for root, _, files in os.walk(DATASET_PATH):
        for file in files:
            if file.endswith(".json"):
                file_path = Path(root) / file
                data = load_graph(file_path)
                data.batch = torch.zeros(data.num_nodes, dtype=torch.long)  # batch=0 since single graph
                data = data.to(device)

                with torch.no_grad():
                    output = model(data)

                if label_mean is not None:
                    output = output * label_std.to(device) + label_mean.to(device)

                pred = output.cpu().numpy().tolist()
                true = data.y.cpu().numpy().tolist()
                print(f"File: {file}, Prediction: {pred}, True: {true}")
                # check if 0 exists in true values
                # TODO: check why this could happen, not usual thouhg
                if any(x == 0 for x in true[0]):
                    print(f"Warning: True values contain zero in {file}. This may affect MAPE calculation.")
                    continue
                # Compute MAE and MAPE per output dimension
                mae_vec = torch.abs(output - data.y).squeeze().cpu()
                mape_vec = (torch.abs((output - data.y) / (data.y + 1e-8))).squeeze().cpu() * 100  # avoid division by zero

                print(f"{file} MAE per element: {[f'{x:.4f}' for x in mae_vec.tolist()]}")
                print(f"{file} MAPE per element: {[f'{x:.2f}%' for x in mape_vec.tolist()]}")

                maes.append(mae_vec)
                mapes.append(mape_vec)

                results[file] = [pred, true]

                if SAVE_RESULTS:
                    out_path = file_path.with_suffix('.pred.json')
                    with open(out_path, "w") as out_file:
                        json.dump({"prediction": pred}, out_file, indent=2)

    # === Summary ===
    maes_tensor = torch.stack(maes)  # shape: [num_samples, 4]
    mapes_tensor = torch.stack(mapes)

    print(f"\n=== MAE Summary ===")
    print("Average MAE per output element:", torch.mean(maes_tensor, dim=0).tolist())
    print("Std of MAE per output element:", torch.std(maes_tensor, dim=0).tolist())

    print(f"\n=== MAPE Summary ===")
    print("Average MAPE per output element:", torch.mean(mapes_tensor, dim=0).tolist())
    print("Std of MAPE per output element:", torch.std(mapes_tensor, dim=0).tolist())



def latency_benchmark():
    data = load_graph(os.path.join(DATASET_PATH, "6_nodes.json"))
    data.batch = torch.zeros(data.num_nodes, dtype=torch.long)  # batch=0 since single graph
    # Move data to device only once
    data = data.to(device)

    # Warm-up pass (important for fair GPU timing)
    for _ in range(10):
        _ = model(data)

    # Actual benchmarking
    NUM_RUNS = 1000
    torch.cuda.synchronize() if device.type == 'cuda' else None
    start = time.time()

    for _ in range(NUM_RUNS):
        with torch.no_grad():
            _ = model(data)
    torch.cuda.synchronize() if device.type == 'cuda' else None
    end = time.time()

    avg_latency_ms = (end - start) / NUM_RUNS * 1000
    print(f"Avg inference latency: {avg_latency_ms:.4f} ms over {NUM_RUNS} runs")


def main():
    parser = argparse.ArgumentParser(description="Run inference.")
    parser.add_argument("--test", action="store_true", help="Run inference on test set")
    parser.add_argument("--benchmark", action="store_true", help="Run latency benchmark")
    args = parser.parse_args()
    if args.test:
        run_test_set()
    elif args.benchmark:
        latency_benchmark()
    else:
        print("Please specify --test or --benchmark.")
        
if __name__ == "__main__":
    main()