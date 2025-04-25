import os
import subprocess
import argparse
import shutil
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
import concurrent.futures
import time
from tqdm import tqdm
import random

def debug_print(*args, **kwargs):
    if True:
        print(*args, **kwargs)

def error_print(*args, **kwargs):
    if True:
        print(*args, **kwargs)

def info_print(*args, **kwargs):
    if True:
        print(*args, **kwargs)

stop_ongoing_process = multiprocessing.Event()

def run_single_smith(smith_executable, p4c_barefoot):
    """
    Runs a single instance of 'smith' until it succeeds.
    """
    attempts = 0
    while True:

        if stop_ongoing_process.is_set():
            return [None,0]
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        folder_name = f"smith_run_{timestamp}_thread-{multiprocessing.current_process().pid}{random.randint(0, 1000000)}"
        try:
            os.makedirs(folder_name)
        except FileExistsError:
            debug_print(f"Folder {folder_name} already exists. Retrying...")
            continue
        attempts += 1
        debug_print(f"Running p4smith in {folder_name}...")
        log_file_path = os.path.join(folder_name, "log.txt")
        timedout = False
        try:
            with open(log_file_path, "w") as log_file:
                smith_exec = [smith_executable, "--target", "tofino", "--arch", "tna", "./smith.p4", "--generate-dag", "--dag-node-num", "6", "--dag-density", "0.6"]
                bf_exec = [p4c_barefoot, "./smith.p4", "-g", "--target", "tofino", "--arch", "tna", "--verbose", "--enable-event-logger", 
                           "--optimized-source","opt.p4", "-Ttable_dependency_graph:3,table_dependency_summary:3,table_placement:5"
                ]

                subprocess.run(smith_exec,
                               stdout=log_file, stderr=log_file, check=True, cwd=folder_name)
                try:
                    subprocess.run(bf_exec, stdout=log_file, stderr=subprocess.STDOUT,
                                check=False, cwd=folder_name, timeout=30)
                except subprocess.TimeoutExpired:
                    timedout = True
                
                log_file.write(f"\n\n\nsmith command: {' '.join(smith_exec)}\n")
                log_file.write(f"p4c_barefoot command: {' '.join(bf_exec)}")

            with open(log_file_path, "r") as log_file:
                log_contents = log_file.read()
                if "0 errors" in log_contents and not timedout:
                    debug_print(f"Success! Output stored in {folder_name}.")
                    return [folder_name, attempts]  # Successful run
                else:
                    debug_print(f"Errors found in output. Deleting {folder_name} and retrying...")
        
        except Exception as e:
            error_print(f"Execution failed: {e}. Deleting {folder_name} and retrying...")
        shutil.rmtree(folder_name)  # Clean up before retrying

def run_smith_parallel(num_repetitions, smith_executable, p4c_barefoot, num_workers):
    """
    Runs 'smith' multiple times in parallel, dynamically retrying failed runs until success count is met.
    """

    def debug_print(*args, **kwargs):
        if True:
            print(*args, **kwargs)
    manager = multiprocessing.Manager()
    success_list = manager.list()
    total_runs_cnt = multiprocessing.Value('i', 0)
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = set()
        progress_bar = tqdm(total=num_repetitions, desc="Successful runs", ncols=80)
        
        while len(success_list) < num_repetitions:
            debug_print(f"Running {num_repetitions - len(success_list)} more repetitions...")
            debug_print(f"Success count: {len(success_list)}")
            debug_print(f"Active workers: {len(futures)}")

            while len(futures) < num_workers and len(success_list) < num_repetitions:

                debug_print(f"Success count: {len(success_list)}")
                info_print(f"Active workers: {len(futures)}")
                futures.add(executor.submit(run_single_smith, smith_executable, p4c_barefoot))
            for future in as_completed(futures):
                futures.remove(future)
                try:
                    result = future.result()
                    if result:
                        with total_runs_cnt.get_lock():
                            success_list.append(result[0])
                            progress_bar.update(1)
                            progress_bar.refresh()
                            total_runs_cnt.value += result[1]
                    if len(success_list) >= num_repetitions:
                        stop_ongoing_process.set()
                        break
                    if len(success_list) < num_repetitions:
                        debug_print(f"Success count: {len(success_list)}")
                        info_print(f"Active workers: {len(futures)}")
                        futures.add(executor.submit(run_single_smith, 
                                                    smith_executable, p4c_barefoot))
                        break # break here so the as_completed(futures) iterator will be updated

                except Exception as e:
                    debug_print(f"Task failed with error: {e}")
                    # Retry failed task
                    futures.add(executor.submit(run_single_smith, smith_executable, p4c_barefoot))
        progress_bar.close()

    
    info_print(f"All {num_repetitions} runs completed successfully.")
    info_print(f"Total runs attempted: {total_runs_cnt.value}")
    ratio = len(success_list) / total_runs_cnt.value if total_runs_cnt.value > 0 else 0
    info_print(f"Success ratio: {ratio:.2%}")
    info_print(f"Success count: {len(success_list)}")

def compile_p4_file(p4_file, p4c_barefoot):
    """
    Compiles a single P4 file and logs output to 'log.txt' in the same folder.
    """
    debug_print(f"Building {p4_file}...")
    log_file_path = os.path.join(os.path.dirname(p4_file), "log.txt")
    with open(log_file_path, "w") as log_file:
        try:
            subprocess.run([
                p4c_barefoot, os.path.basename(p4_file), "-g", "--target", "tofino", "--arch", "tna","--verbose", "--enable-event-logger", "--optimized-source","opt.p4", "-Ttable_dependency_graph:3,table_dependency_summary:3,table_placement:5"
                ], stdout=log_file, stderr=log_file, check=True, cwd=os.path.dirname(p4_file), timeout=40)
        except Exception as e:
            debug_print(f"Error compiling {p4_file}: {e}")
            # remove the folder file if compilation fails -> too dangerous
            # try:
            #     shutil.rmtree(os.path.dirname(p4_file))
            # except Exception as e:
            #     debug_print(f"Error removing folder {os.path.dirname(p4_file)}: {e}")

def build_p4_programs_recursive(p4c_barefoot, build_only_dir, num_workers):
    """
    Recursively builds all P4 programs in the current directory and subdirectories.
    """
    p4_files = []
    for root, _, files in os.walk(build_only_dir):
        for file in files:
            if file.endswith(".p4"):
                p4_files.append(os.path.join(root, file))
    debug_print(f"Found {len(p4_files)} P4 programs. Compiling with {num_workers} workers...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(compile_p4_file, p4_file, p4c_barefoot) for p4_file in p4_files}
        concurrent.futures.wait(futures)

def run_p4c_build_logs(p4c_build_logs,relative_folder, num_workers, build_only_dir):
    """
    Recursively searches for P4 programs and runs p4c-build-logs in each folder.
    """
    p4_files = []
    for root, _, files in os.walk(build_only_dir):
        for file in files:
            if file.endswith("opt.p4"):
                p4_files.append(os.path.join(root, file))

    debug_print(f"Found {len(p4_files)} P4 programs. Running p4c-build-logs with {num_workers} workers...")


    link_phv_cmd = ["ln", "-s", os.path.join("./logs", "phv.json"), os.path.join("./phv.json")]
    for p4_file in p4_files:
        subprocess.run(link_phv_cmd, cwd=os.path.join(os.path.dirname(p4_file), relative_folder
        ))
    commands = [
        [
            p4c_build_logs,
            os.path.join("./context.json"),
            "--manifest", os.path.join("../manifest.json"),
            "--power", os.path.join("./logs/power.json"),
            "--resources", os.path.join("./logs/resources.json"),
            "--disable-phv-json"
        ]
        for p4_file in p4_files
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            executor.submit(
                subprocess.run,
                cmd,
                stdout=open(os.path.join(os.path.dirname(p4_file),relative_folder, "log.txt"), "w"),
                stderr=subprocess.STDOUT,
                check=True,
                cwd=os.path.join(os.path.dirname(p4_file), relative_folder)
            )
            for cmd, p4_file in zip(commands, p4_files)
        }
        concurrent.futures.wait(futures)

def main():
    parser = argparse.ArgumentParser(description="Run 'smith' executable multiple times in parallel and store outputs.")
    parser.add_argument("-n", "--num-repetitions", type=int, help="Number of successful repetitions required.")
    parser.add_argument("-e", "--smith-executable", type=str, default="", help="Full path to the 'smith' executable.")
    parser.add_argument("-c", "--p4c-barefoot", type=str, default="", help="Full path to the 'p4c-barefoot' executable.")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of parallel workers (default: 4).")
    parser.add_argument("-b", "--build-only", action="store_true", help="Build all p4 programs in current directory recursively.")
    parser.add_argument("-b-dir", "--build-only-dir", type=str, default="", help="build_p4_programs_recursive")
    parser.add_argument("--p4c-build-logs", type=str, default="", help="Full path to the 'p4c-build-logs' executable.")
    
    args = parser.parse_args()
    if  args.smith_executable != "" and os.path.exists(args.smith_executable):
        run_smith_parallel(args.num_repetitions, args.smith_executable, args.p4c_barefoot, args.workers)
        return

    if args.build_only and args.build_only_dir != "" and os.path.exists(args.build_only_dir) and args.p4c_barefoot != "":
        build_p4_programs_recursive(args.p4c_barefoot, args.build_only_dir, args.workers)
        return
    
    if args.p4c_build_logs != "" and os.path.exists(args.p4c_build_logs) and args.build_only_dir != "":
        run_p4c_build_logs(args.p4c_build_logs, "smith.tofino/pipe", args.workers, args.build_only_dir)
        return
    debug_print("Nothing run, check the arguments")

if __name__ == "__main__":
    main()