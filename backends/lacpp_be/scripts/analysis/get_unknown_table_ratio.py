# this script is used to get the ratio of unknown tables to total tables in a program
# try to see if there is a correlation between the accuracy of prediction (mape)
# and the ratio of unknown tables.

#input: dir containing json files for features
import os
import json
import argparse
parser = argparse.ArgumentParser(description="Get the ratio of unknown tables in JSON files.")
parser.add_argument("--dir", type=str, default="data/", help="Directory containing JSON files.")


for root, dirs, files in os.walk(parser.parse_args().dir):
    for file in files:
        if file.endswith(".json"):
            tables = []
            with open(os.path.join(root, file), "r") as f:
                data = json.load(f)
                if "nodes" not in data:
                    continue
                num_total_nodes = len(data["nodes"])
                unknown_cnt = 0
                for i, node_attr in enumerate(data["node_attr"]):
                    if node_attr[5] == 1:
                        unknown_cnt += 1
                        
            ratio = unknown_cnt / num_total_nodes
            print(f"{file}: ratio: {ratio:.2f} unknown_cnt: {unknown_cnt} total: {num_total_nodes}")

                    