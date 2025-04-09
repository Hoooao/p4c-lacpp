import torch
import torch.nn as nn
import torch.optim as optim
from torch_geometric.nn import GATConv, global_mean_pool
from torch_geometric.data import Data, Dataset, DataLoader as GeoDataLoader

import os
import pickle
from time import time
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModel
import json

USE_GPU = True
BATCH_SIZE = 1
EPOCHS = 100
LEARNING_RATE = 0.001
MODEL_SAVE_PATH = "performance_predictor.pth"
EMBEDDING_CACHE = "codebert_embeddings.pkl"

# Device selection
device = torch.device("cuda" if USE_GPU and torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Dataset using node features and adjacency from file
class CodeGraphDataset(Dataset):
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.samples = self._load_samples()

    def _load_samples(self):
        samples = []
        from pathlib import Path
        for file in Path(self.folder_path).rglob("*.p4"):
            base = file.stem
            node_feat_file = file.parent / f"{base}_nodes.pt"
            edge_index_file = file.parent / f"{base}_edges.pt"
            label_file = file.parent / "perf.txt"

            if not (node_feat_file.exists() and edge_index_file.exists() and label_file.exists()):
                continue

            x = torch.load(node_feat_file)  # Tensor [num_nodes, feat_dim]
            edge_index = torch.load(edge_index_file)  # Tensor [2, num_edges]
            with open(label_file, "r") as f:
                a, b = map(float, f.read().strip().split(","))
            y = torch.tensor([a, b], dtype=torch.float32)
            samples.append(Data(x=x, edge_index=edge_index, y=y))
        return samples

    def len(self):
        return len(self.samples)

    def get(self, idx):
        return self.samples[idx]

# GAT model for graph-level prediction
class GATPerformanceModel(nn.Module):
    def __init__(self, in_dim=768, hidden_dim=128, out_dim=2):
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

# Weighted MSE loss
class WeightedMSELoss(nn.Module):
    def __init__(self, weights):
        super().__init__()
        self.weights = torch.tensor(weights).to(device)

    def forward(self, outputs, targets):
        loss = (outputs - targets) ** 2
        return (loss * self.weights).mean()

# Training function
def train_model(model, dataloader):
    criterion = WeightedMSELoss([100, 1])
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=0.5)

    model.train()
    loss_history = []

    for epoch in range(EPOCHS):
        total_loss = 0
        start_time = time()
        for batch in tqdm(dataloader, desc=f"Epoch {epoch+1}/{EPOCHS}"):
            batch = batch.to(device)
            optimizer.zero_grad()
            outputs = model(batch)
            loss = criterion(outputs, batch.y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        scheduler.step()

        avg_loss = total_loss / len(dataloader)
        loss_history.append(avg_loss)
        print(f"Epoch {epoch+1}/{EPOCHS}, Loss: {avg_loss:.2f}")
        torch.save(model.state_dict(), MODEL_SAVE_PATH)

    return loss_history

# Main
if __name__ == "__main__":
    folder_path = "../dataset"
    dataset = CodeGraphDataset(folder_path)
    dataloader = GeoDataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    model = GATPerformanceModel().to(device)
    loss_history = train_model(model, dataloader)

    import matplotlib.pyplot as plt 
    plt.plot(loss_history)
    plt.title("Training Loss Curve")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.grid(True)
    plt.savefig("loss_curve.png")
    plt.show()
