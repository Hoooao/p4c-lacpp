import os
import subprocess
import argparse
import shutil
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

def run_single_smith(smith_executable, p4c_barefoot):
    """
    Runs a single instance of 'smith' until it succeeds.
    """
    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder_name = f"smith_run_{timestamp}_thread-{multiprocessing.current_process().pid}"
        os.makedirs(folder_name, exist_ok=True)
        
        print(f"Running p4smith in {folder_name}...")
        log_file_path = os.path.join(folder_name, "log.txt")

        try:
            with open(log_file_path, "w") as log_file:
                subprocess.run([smith_executable, "--target", "tofino", "--arch", "tna", "./smith.p4", "--generate-dag", "--dag-node-num", "4", "--dag-density", "0.6"],
                               stdout=log_file, stderr=log_file, check=True, cwd=folder_name)
                
                subprocess.run([p4c_barefoot, "./smith.p4", "-g", "--target", "tofino", "--arch", "tna", "--create-graphs"], stdout=log_file, stderr=subprocess.STDOUT,
                               check=False, cwd=folder_name)

            with open(log_file_path, "r") as log_file:
                log_contents = log_file.read()
                if "0 errors" in log_contents:
                    print(f"Success! Output stored in {folder_name}.")
                    return folder_name  # Successful run
                else:
                    print(f"Errors found in output. Deleting {folder_name} and retrying...")
        
        except subprocess.CalledProcessError as e:
            print(f"Execution failed: {e}. Deleting {folder_name} and retrying...")
        shutil.rmtree(folder_name)  # Clean up before retrying

def run_smith_parallel(num_repetitions, smith_executable, p4c_barefoot, num_workers):
    """
    Runs 'smith' multiple times in parallel, dynamically retrying failed runs until success count is met.
    """
    manager = multiprocessing.Manager()
    success_list = manager.list()
    
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = set()
        
        while len(success_list) < num_repetitions:
            print(f"Running {num_repetitions - len(success_list)} more repetitions...")
            print(f"Success count: {len(success_list)}")
            print(f"Active workers: {len(futures)}")

            while len(futures) < num_workers and len(success_list) + len(futures) < num_repetitions:
                futures.add(executor.submit(run_single_smith, smith_executable, p4c_barefoot))
            for future in as_completed(futures):
                futures.remove(future)
                try:
                    result = future.result()
                    if result:
                        success_list.append(result)
                    # Immediately submit a new task if more successes are needed
                    if len(success_list) < num_repetitions:
                        futures.add(executor.submit(run_single_smith, smith_executable, p4c_barefoot))
                except Exception as e:
                    print(f"Task failed with error: {e}")
                    # Retry failed task
                    futures.add(executor.submit(run_single_smith, smith_executable, p4c_barefoot))

    
    print(f"All {num_repetitions} runs completed successfully.")

def main():
    parser = argparse.ArgumentParser(description="Run 'smith' executable multiple times in parallel and store outputs.")
    parser.add_argument("-n", "--num-repetitions", type=int, required=True, help="Number of successful repetitions required.")
    parser.add_argument("-e", "--smith-executable", type=str, required=True, help="Full path to the 'smith' executable.")
    parser.add_argument("-c", "--p4c-barefoot", type=str, required=True, help="Full path to the 'p4c-barefoot' executable.")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of parallel workers (default: 4).")
    
    args = parser.parse_args()
    run_smith_parallel(args.num_repetitions, args.smith_executable, args.p4c_barefoot, args.workers)

if __name__ == "__main__":
    main()