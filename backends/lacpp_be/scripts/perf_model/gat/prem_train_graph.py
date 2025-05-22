import torch
import torch.nn as nn
import torch.optim as optim
from torch_geometric.nn import GATConv, global_mean_pool
from torch_geometric.data import Data, Dataset
from torch_geometric.loader import DataLoader as GeoDataLoader

import os
import json
from pathlib import Path
from time import time
from tqdm import tqdm
import matplotlib.pyplot as plt

USE_GPU = True
BATCH_SIZES = [1,2,4,8,16,32,64]
EPOCHS = 500
LEARNING_RATE = 0.001

# Device selection
device = torch.device("cuda" if USE_GPU and torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Custom Dataset from JSON
class CodeGraphJSONDataset(Dataset):
    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path
        self.samples = self._load_samples()

    def _load_samples(self):
        samples = []
        for file in Path(self.folder_path).rglob("*.json"):
            with open(file, "r") as f:
                js = json.load(f)

            x = torch.tensor(js["node_attr_normalized"], dtype=torch.float)  # [num_nodes, feat_dim]
            edge_index = torch.tensor(js["edge_index"], dtype=torch.long)  # [2, num_edges]
            edge_attr = torch.tensor(
                [[int(b) for b in s] for s in js["edge_attr"]],
                dtype=torch.float
            )  # [num_edges, bit_vector_len]
            y = torch.tensor(js["y_normalized"], dtype=torch.float).unsqueeze(0)  

            data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr, y=y)
            samples.append(data)
        return samples

    def len(self):
        return len(self.samples)

    def get(self, idx):
        return self.samples[idx]

# GAT model with edge_attr support (currently ignored, placeholder for future use)
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


# Training function
def train_model(model, dataloader, batch_size=1):
    criterion = nn.MSELoss()
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
        torch.save(model.state_dict(), f"performance_predictor_b{batch_size}.pth")

    return loss_history

# Main
if __name__ == "__main__":
    folder_path = "./dataset"
    dataset = CodeGraphJSONDataset(folder_path)
    for batch_size in BATCH_SIZES:
        dataloader = GeoDataLoader(dataset, batch_size=batch_size, shuffle=True)

        model = GATPerformanceModel().to(device)
        loss_history = train_model(model, dataloader, batch_size)

        plt.plot(loss_history)
        plt.title("Training Loss Curve")
        plt.xlabel("Epoch")
        plt.ylabel("Loss")
        plt.grid(True)
        plt.savefig(f"loss_curve_b{batch_size}.png")
        plt.show()
