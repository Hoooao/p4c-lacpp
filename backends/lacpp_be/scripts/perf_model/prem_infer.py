import torch
import os
import json
from time import time
from transformers import AutoTokenizer, AutoModel
from tqdm import tqdm
import argparse
MODEL_PATH = "performance_predictor.pth"

# ==============================
# Configuration
# ==============================
USE_GPU = True  # Set False for CPU inference

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
        self.model.eval().to(device)  # Load model to GPU or CPU

    def get_embedding(self, code_snippet):
        tokens = self.tokenizer(code_snippet, return_tensors="pt", padding=True, truncation=True, max_length=512).to(device)
        with torch.no_grad():
            output = self.model(**tokens).last_hidden_state
        embedding = output.mean(dim=1)  # Mean pooling
        return embedding 

# ==============================
# Load Trained Model
# ==============================
class PerformancePredictor(torch.nn.Module):
    def __init__(self, input_dim=768, hidden_dim=512, output_dim=2):
        super(PerformancePredictor, self).__init__()
        self.fc1 = torch.nn.Linear(input_dim, hidden_dim)
        self.fc2 = torch.nn.Linear(hidden_dim, hidden_dim // 2)
        self.fc3 = torch.nn.Linear(hidden_dim // 2, output_dim)
        self.relu = torch.nn.ReLU()
        self.dropout = torch.nn.Dropout(0.2)  # Prevent overfitting

    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.relu(self.fc2(x))
        x = self.fc3(x)  # Output 3-element vector
        return x

# Load the trained model
model = PerformancePredictor().to(device)
model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
model.eval()
print("Model loaded successfully.")

# ==============================
# Function to Load Programs for Inference
# ==============================
def load_programs(folder_path):
    code_samples = []
    filenames = sorted(os.listdir(folder_path))

    for filename in filenames:
        if filename.endswith(".p4"):
            with open(os.path.join(folder_path, filename), "r", encoding="utf-8") as file:
                code_samples.append((filename, file.read()))  # Store filename and code content

    return code_samples

def predict_performance(folder_path, embedder, model):
    programs = load_programs(folder_path)
    results = {}
    
    print("Generating predictions...")
    for filename, code in tqdm(programs):
        if torch.cuda.is_available():
            torch.cuda.synchronize()  
        start_time = time()

        embedding = embedder.get_embedding(code).to(device)
        with torch.no_grad():
            output = model(embedding)

        if torch.cuda.is_available():
            torch.cuda.synchronize()  
        end_time = time()
        prediction = output.cpu().numpy().tolist()

        # Step 4: Save results
        results[filename] = prediction

        # Optional: Print timing for this sample
    execution_time = (end_time - start_time) * 1000 

    # Save results as JSON
    output_file = "inference_results.json"
    output_data = {
        "predictions": results,
        "execution_time": execution_time  
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4)

    print(f"Inference complete. Results saved to {output_file} (Time taken: {execution_time:.2f} ms)")


# ==============================
# Run Inference
# ==============================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inference")
    parser.add_argument("-f", "--input-p4-file", type=str, required=True, help="The input p4 file.")
    args = parser.parse_args()
    embedder = CodeBERTEmbedding()
    predict_performance(args.input_p4_file, embedder, model)
