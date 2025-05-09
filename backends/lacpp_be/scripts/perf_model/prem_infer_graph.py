import torch
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader as GeoDataLoader
from pathlib import Path
import json
import os
import time
import torch.nn as nn
from torch_geometric.nn import GATConv, global_mean_pool
import argparse

# === Config ===
MODEL_PATH = "performance_predictor.pth"
DATASET_PATH = "./test_set"
USE_GPU = True
SAVE_RESULTS = False  # Save predictions per file
NORMALIZATION_STATS = "label_norm.json"  # optional

device = torch.device("cuda" if USE_GPU and torch.cuda.is_available() else "cpu")

# === Load normalization stats ===
if os.path.exists(NORMALIZATION_STATS):
    with open(NORMALIZATION_STATS) as f:
        norm_stats = json.load(f)
        label_mean = torch.tensor(norm_stats["mean"])
        label_std = torch.tensor(norm_stats["std"])
else:
    label_mean = label_std = None

class GATPerformanceModel(nn.Module):
    def __init__(self, in_dim=6, hidden_dim=128, out_dim=4):
        super().__init__()
        self.gat1 = GATConv(in_dim, hidden_dim, heads=4, concat=True)
        self.gat2 = GATConv(hidden_dim * 4, hidden_dim, heads=1, concat=False)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, out_dim)
        )

    def forward(self, data):
        x, edge_index, batch = data.x, data.edge_index, data.batch
        x = self.gat1(x, edge_index).relu()
        x = self.gat2(x, edge_index).relu()
        x = global_mean_pool(x, batch)
        return self.mlp(x)
# === Load model ===
model = GATPerformanceModel(in_dim=6, hidden_dim=128, out_dim=4)
model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
model.to(device)
model.eval()

def run_test_set():
    # === Inference on all graphs in folder ===
    results = {}
    for file in Path(DATASET_PATH).rglob("*.json"):
        with open(file) as f:
            js = json.load(f)

        x = torch.tensor(js["node_attr_normalized"], dtype=torch.float)
        edge_index = torch.tensor(js["edge_index"], dtype=torch.long)
        edge_attr = torch.tensor(
            [[int(b) for b in s] for s in js["edge_attr"]],
            dtype=torch.float
        )

        data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
        data.batch = torch.zeros(data.num_nodes, dtype=torch.long)  # batch=0 since single graph
        data = data.to(device)

        with torch.no_grad():
            output = model(data)

        if label_mean is not None:
            output = output * label_std.to(device) + label_mean.to(device)

        pred = output.cpu().numpy().tolist()
        results[file.name] = pred

        if SAVE_RESULTS:
            out_path = file.with_name(file.stem + "_prediction.json")
            with open(out_path, "w") as out_file:
                json.dump({"prediction": pred}, out_file, indent=2)

    # === Print summary ===
    for fname, pred in results.items():
        print(f"{fname}: {pred}")

def latency_benchmark():
    with open(os.path.join(DATASET_PATH, "6_nodes.json")) as f:
        js = json.load(f)
    x = torch.tensor(js["node_attr_normalized"], dtype=torch.float)
    edge_index = torch.tensor(js["edge_index"], dtype=torch.long)
    edge_attr = torch.tensor(
        [[int(b) for b in s] for s in js["edge_attr"]],
        dtype=torch.float
    )
    data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
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