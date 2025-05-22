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
MODEL_PATH = "./b4_2000/performance_predictor_b4.pth"
DATASET_PATH = "./dataset/part-5"
USE_GPU = True
SAVE_RESULTS = False  # Save predictions per file
NORMALIZATION_STATS = "means_stds.json"  # optional

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
    # fill it to 20elements with 0s if less than 20
    bitmap = []
    for bits in edge_attr_strings:
        # convert to list of int
        bits = [int(b) for b in bits]
        # fill it to 20elements with 0s if less than 20
        bits = [0] * (20 - len(bits)) + bits
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
    y          = torch.tensor(js["y_normalized"],
                            dtype=torch.float).unsqueeze(0)
    return Data(x=x, edge_index=edge_index, edge_attr=edge_attr, y=y)

def run_test_set():
    # === Inference on all graphs in folder ===
    results = {}
    for file in Path(DATASET_PATH).rglob("*.json"):
        data = load_graph(file)
        data.batch = torch.zeros(data.num_nodes, dtype=torch.long)  # batch=0 since single graph
        data = data.to(device)

        with torch.no_grad():
            output = model(data)

        # if label_mean is not None:
        #     output = output * label_std.to(device) + label_mean.to(device)

        pred = output.cpu().numpy().tolist()
        results[file.name] = pred
        # MAE for all 4 outputs
        mae = torch.mean(torch.abs(output - data.y)).item()
        print(f"MAE for {file.name}: {mae:.4f}")
        mape = torch.mean(torch.abs((output - data.y) / data.y)).item() * 100
        print(f"MAPE for {file.name}: {mape:.4f}")

        if SAVE_RESULTS:
            out_path = file.with_name(file.stem + "_prediction.json")
            with open(out_path, "w") as out_file:
                json.dump({"prediction": pred}, out_file, indent=2)

    # === Print summary ===
    for fname, pred in results.items():
        print(f"{fname}: {pred}")

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