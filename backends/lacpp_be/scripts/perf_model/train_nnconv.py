import torch
import torch.nn as nn
import torch.optim as optim
from torch_geometric.nn import NNConv, global_mean_pool
from torch_geometric.data import Data, Dataset
from torch_geometric.loader import DataLoader as GeoDataLoader

import os
import json
from pathlib import Path
from time import time
from tqdm import tqdm
import matplotlib.pyplot as plt

USE_GPU = True
BATCH_SIZES = [4] #[1,2,4,8,16,32,64]
EPOCHS = 100
LEARNING_RATE = 0.0005
DATASET_NUMBER = 4 # say 2, means include part-0, part-1, part-2
PATIENCE = 12
NAME = "hid64_b4"  # Name of the model, used for saving

torch.set_num_threads(torch.get_num_threads())
# Device selection
device = torch.device("cuda" if USE_GPU and torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")    

class CodeGraphJSONDataset(Dataset):
    """
    • Each *.json file must contain:
        - node_attr_normalized :  List[List[float]]
        - edge_index           :  List[List[int]]
        - edge_attr            :  List[str]          (bit-strings like "101")
        - y_normalized         :  List[float]
    """
    def __init__(self, folder_path, dataset_number=0, is_validation=False):
        super().__init__()
        self.folder_path = Path(folder_path)
        self.dataset_number = dataset_number
        self.is_validation = is_validation
        self.samples = self._load_samples()

    # --------------------------------------------------------------------- #
    def _edge_bits_to_tensor(self, edge_attr_strings):
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

    def _load_samples(self):
        samples = []
        folders = []
        # seach for folders with part-*
        for folder in self.folder_path.iterdir():
            if folder.is_dir() and folder.name.startswith("part-"):
                folders.append(folder)
        folders.sort()
        print(f"Found {len(folders)} folders: {[f.name for f in folders]}")
        start = 0
        if self.is_validation:
            start = self.dataset_number + 1
            end = start + 1
        else:
            end = self.dataset_number + 1
        for folder in folders[start:end]:
            for file in folder.rglob("*.json"):
                with open(file, "r") as f:
                    js = json.load(f)

                x          = torch.tensor(js["node_attr_normalized"],
                                        dtype=torch.float)            # [N, F]
                edge_index = torch.tensor(js["edge_index"],
                                        dtype=torch.long)             # [2, E]
                edge_attr  = self._edge_bits_to_tensor(js["edge_attr"])  # [E, B]
                y          = torch.tensor(js["y_normalized"],
                                        dtype=torch.float).unsqueeze(0)

                samples.append(Data(x=x,
                                    edge_index=edge_index,
                                    edge_attr=edge_attr,
                                    y=y))
        if self.is_validation:
            print(f"Validation dataset loaded from folder {start}.")
        else:
            print(f"Training dataset loaded from folders 0 to {self.dataset_number}.")
        return samples

    # --------------------------------------------------------------------- #
    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


# ------------------------------  NN-based model ------------------------------
class NNConvPerformanceModel(nn.Module):
    """
    Edge-aware GNN for P4 performance prediction.
    • node features  : data.x            ∈ ℝ[in_dim]
    • edge features  : data.edge_attr    ∈ ℝ[edge_dim]
    • target         : data.y           ∈ ℝ[out_dim]
    """
    def __init__(self,
                 in_dim: int        = 6,
                 edge_dim: int      = 3,   # len(js["edge_attr"][0])
                 hidden_dim: int    = 128,
                 out_dim: int       = 4):
        super().__init__()
        self.dropout = nn.Dropout(p=0.10)
        # --- 1st NNConv layer -------------------------------------------------
        # The inner MLP maps each edge-feature vector e_ij  ↦  W_ij  (in×hidden)
        nn1 = nn.Sequential(
            nn.Linear(edge_dim, in_dim * hidden_dim),
            nn.ReLU(),
            nn.Linear(in_dim * hidden_dim, in_dim * hidden_dim)
        )
        self.conv1 = NNConv(in_channels=in_dim,
                            out_channels=hidden_dim,
                            nn=nn1,
                            aggr='mean')

        # --- 2nd NNConv layer -------------------------------------------------
        nn2 = nn.Sequential(
            nn.Linear(edge_dim, hidden_dim * hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim * hidden_dim, hidden_dim * hidden_dim)
        )
        self.conv2 = NNConv(in_channels=hidden_dim,
                            out_channels=hidden_dim,
                            nn=nn2,
                            aggr='mean')
        
        # --- 3rd NNConv layer (optional) --------------------------------------
        nn3 = nn.Sequential(
            nn.Linear(edge_dim, hidden_dim * hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim * hidden_dim, hidden_dim * hidden_dim)
        )
        self.conv3 = NNConv(in_channels=hidden_dim,
                            out_channels=hidden_dim,
                            nn=nn3,
                            aggr='mean')

        # --- MLP head ---------------------------------------------------------
        self.mlp = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, out_dim)
        )

    def forward(self, data):
        x, edge_index, edge_attr, batch = \
            data.x, data.edge_index, data.edge_attr, data.batch
        x = self.dropout(x)
        x = self.conv1(x, edge_index, edge_attr).relu()
        x = self.conv2(x, edge_index, edge_attr).relu()
        x = self.conv3(x, edge_index, edge_attr).relu()

        # graph-level read-out
        x = global_mean_pool(x, batch)
        return self.mlp(x)

# Training function
def train_model(model, train_loader, val_loader, batch_size=1):
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=0.5)

    model = model.to(device)
    loss_history = []
    val_loss_history = []

    best_val_loss = float('inf')
    patience_counter = 0

    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0

        for batch in tqdm(train_loader, desc=f"Epoch {epoch+1}/{EPOCHS}"):
            batch = batch.to(device)
            optimizer.zero_grad()
            outputs = model(batch)
            loss = criterion(outputs, batch.y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        
        scheduler.step()
        avg_train_loss = round(total_loss / len(train_loader), 5)
        loss_history.append(avg_train_loss)

        # --- Validation ---
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(device)
                outputs = model(batch)
                loss = criterion(outputs, batch.y)
                val_loss += loss.item()
        avg_val_loss = round(val_loss / len(val_loader), 5)
        val_loss_history.append(avg_val_loss)

        print(f"Epoch {epoch+1}/{EPOCHS}, Train Loss: {avg_train_loss:.5f}, Val Loss: {avg_val_loss:.5f}, patience: {patience_counter}")

        # Save best model
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            torch.save(model.state_dict(), f"{NAME}_best_model.pth")
        else:
            patience_counter += 1
            if patience_counter >= PATIENCE:
                print(f"Early stopping at epoch {epoch+1}")
                break

    return loss_history, val_loss_history

# Main
if __name__ == "__main__":
    folder_path = "./dataset"
    dataset = CodeGraphJSONDataset(folder_path, DATASET_NUMBER)
    val_set = CodeGraphJSONDataset(folder_path, DATASET_NUMBER, is_validation=True)
    for batch_size in BATCH_SIZES:
        dataloader = GeoDataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=4)
        val_dataloader = GeoDataLoader(val_set, batch_size=batch_size, shuffle=False, num_workers=4)
        model = NNConvPerformanceModel().to(device)
        [loss_history, val_history] = train_model(model, dataloader, val_dataloader, batch_size)
        # save loss history
        with open(f"{NAME}_loss_history.json", "w") as f:
            json.dump(loss_history, f)
        with open(f"{NAME}_val_loss_history.json", "w") as f:
            json.dump(val_history, f)
        plt.plot(loss_history)
        plt.plot(val_history)
        plt.legend(["Training Loss", "Validation Loss"])
        plt.title("Training Loss Curve")
        plt.xlabel("Epoch")
        plt.ylabel("Loss")
        plt.grid(True)
        plt.savefig(f"{NAME}_loss_curve.png")
        plt.show()
