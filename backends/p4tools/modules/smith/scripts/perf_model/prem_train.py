import torch
import torch.nn as nn
import torch.optim as optim

import os
import json
import pickle
from time import time
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModel
from torch.utils.data import Dataset, DataLoader

# ==============================
# Configuration Settings
# ==============================
USE_GPU = True  # Set to False if running on CPU
BATCH_SIZE = 1
EPOCHS = 100
LEARNING_RATE = 0.001
MODEL_SAVE_PATH = "performance_predictor.pth"
EMBEDDING_CACHE = "codebert_embeddings.pkl"

# Select device
device = torch.device("cuda" if USE_GPU and torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# ==============================
# Load CodeBERT for Embedding Extraction
# ==============================
class CodeBERTEmbedding:
    def __init__(self, model_name="microsoft/codebert-base"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.eval().to(device)  # Move model to selected device

    def get_embedding(self, code_snippet):
        tokens = self.tokenizer(code_snippet, return_tensors="pt", padding=True, truncation=True, max_length=512).to(device)
        with torch.no_grad():
            output = self.model(**tokens).last_hidden_state
        embedding = output.mean(dim=1)  # Mean pooling
        return embedding.cpu()  # Move to CPU to save memory

# ==============================
# Read Programs and Labels from Folder
# ==============================
def load_programs_and_labels(root_dir):
    """
    Recursively finds P4 programs and loads their code along with associated labels from 'perf.txt'.
    """
    code_samples = []
    labels = []
    print(f"Loading programs and labels from {root_dir}...")
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".p4"):
                program_path = os.path.join(root, file)
                label_path = os.path.join(root, "perf.txt")
                
                with open(program_path, "r", encoding="utf-8") as file:
                    code_samples.append(file.read())
                
                if os.path.exists(label_path):
                    with open(label_path, "r", encoding="utf-8") as file:
                        try:
                            a, b = map(int, file.read().strip().split(','))
                            labels.append((a, b))
                        except ValueError:
                            raise ValueError(f"Invalid format in {label_path}. Expected two numbers separated by a comma.")
                else:
                    raise FileNotFoundError(f"Label file missing for {program_path}")
    print(f"Loaded {len(code_samples)} code samples and {len(labels)} labels.")
    return code_samples, labels

# ==============================
# Dataset with Precomputed Embeddings
# ==============================
class CodeDataset(Dataset):
    def __init__(self, folder_path, embedder):
        self.folder_path = folder_path
        self.embedder = embedder
        self.embeddings, self.labels = self._get_or_generate_embeddings()

    def _get_or_generate_embeddings(self):
        if os.path.exists(EMBEDDING_CACHE):
            print("Loading precomputed embeddings...")
            with open(EMBEDDING_CACHE, "rb") as f:
                data = pickle.load(f)
            return data["embeddings"], data["labels"]
        
        print("Generating embeddings from CodeBERT...")
        code_samples, labels = load_programs_and_labels(self.folder_path)
        embeddings = [self.embedder.get_embedding(code).squeeze(0) for code in tqdm(code_samples)]
        
        with open(EMBEDDING_CACHE, "wb") as f:
            pickle.dump({"embeddings": embeddings, "labels": labels}, f)
        return embeddings, labels

    def __len__(self):
        return len(self.embeddings)

    def __getitem__(self, idx):
        return self.embeddings[idx].to(device), torch.tensor(self.labels[idx], dtype=torch.float32).to(device)

# ==============================
# Define Deep Learning Model
# ==============================
class PerformancePredictor(nn.Module):
    def __init__(self, input_dim=768, hidden_dim=512, output_dim=2):
        super(PerformancePredictor, self).__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim // 2)
        self.fc3 = nn.Linear(hidden_dim // 2, output_dim)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.2)  # Prevent overfitting

    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.relu(self.fc2(x))
        x = self.fc3(x)  # Output 3-element vector
        return x

# ==============================
# Training Function
# ==============================
class WeightedMSELoss(nn.Module):
    def __init__(self, weights):
        super().__init__()
        self.weights = torch.tensor(weights).to(device)

    def forward(self, outputs, targets):
        loss = (outputs - targets) ** 2
        return (loss * self.weights.to(outputs.device)).mean()

def train_model(model, dataloader, epochs=EPOCHS, lr=LEARNING_RATE):
    criterion = WeightedMSELoss(weights = [100,1])
    optimizer = optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=0.5)  # Reduce LR every 10 epochs

    model.train()
    loss_history = []

    for epoch in range(epochs):
        total_loss = 0
        start_time = time()
        for inputs, targets in tqdm(dataloader, desc=f"Epoch {epoch+1}/{epochs}"):
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, targets)
            #print(f"Loss: {loss.item()}  pred: {outputs}  targets: {targets}")
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        end_time = time()
        epoch_time = end_time - start_time
        avg_loss = total_loss / len(dataloader)
        loss_history.append(avg_loss)

        scheduler.step()
        print(f"Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.4f}, Time taken: {epoch_time * 1000:.2f} ms")

        # Save model checkpoint
        torch.save(model.state_dict(), MODEL_SAVE_PATH)
        print(f"Checkpoint saved at {MODEL_SAVE_PATH}")
    print(loss_history)


# ==============================
# Load Data and Train
# ==============================
if __name__ == "__main__":
    folder_path = "../dataset"
    embedder = CodeBERTEmbedding()
    dataset = CodeDataset(folder_path, embedder)
    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)

    model = PerformancePredictor().to(device)
    train_model(model, dataloader)
