import os
import subprocess
import argparse
import shutil
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
import concurrent.futures
from tqdm import tqdm
import random

def debug_print(*args, **kwargs):
    if False:
        print(*args, **kwargs)

def error_print(*args, **kwargs):
    if False:
        print(*args, **kwargs)

def info_print(*args, **kwargs):
    if False:
        print(*args, **kwargs)

stop_ongoing_process = multiprocessing.Event()

def run_single_smith(smith_executable, p4c_barefoot):
    """
    Runs a single instance of 'smith' until it succeeds.
    """
    attempts = 0
    while True:

        if stop_ongoing_process.is_set():
            return [None,attempts]
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
                smith_exec = [smith_executable, "--target", "tofino", "--arch", "tna", "./smith.p4", "--generate-dag", "--dag-node-num", "9", "--dag-density", "0.6"]
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

            found_zero_errors = False
            with open(log_file_path, "r") as log_file:
                found_zero_errors = any(line.startswith("0 errors") for line in log_file)

            if found_zero_errors and not timedout:
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
        if False:
            print(*args, **kwargs)
    manager = multiprocessing.Manager()
    success_list = manager.list()
    total_runs_cnt = multiprocessing.Value('i', 0)
    start_time = datetime.now()
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
                    [result, count] = future.result()
                    with total_runs_cnt.get_lock():
                        if result:
                            success_list.append(result)
                            progress_bar.update(1)
                            progress_bar.refresh()
                        total_runs_cnt.value += count
                    if len(success_list) >= num_repetitions:
                        stop_ongoing_process.set()
                        break
                    if len(success_list) < num_repetitions:
                        debug_print(f"Success count: {len(success_list)}")
                        debug_print(f"Active workers: {len(futures)}")
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
    info_print(f"Total time taken: {datetime.now() - start_time}")
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
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(compile_p4_file, p4_file, p4c_barefoot) for p4_file in p4_files}
        concurrent.futures.wait(futures)

def run_single_p4c_build_logs(cmd, p4_file, relative_folder):
    try:
        log_path = os.path.join(os.path.dirname(p4_file), relative_folder, "log.txt")
        cwd = os.path.join(os.path.dirname(p4_file), relative_folder)
        os.makedirs(cwd, exist_ok=True)
        with open(log_path, "w") as log_file:
            subprocess.run(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                check=True,
                cwd=cwd
            )
        return (p4_file, "success")
    except Exception as e:
        return (p4_file, f"unexpected error: {str(e)}")
        
def run_p4c_build_logs(p4c_build_logs,relative_folder, num_workers, build_only_dir):
    """
    Recursively searches for P4 programs and runs p4c-build-logs in each folder.
    """

    #check if the p4c_build_logs exists
    if not os.path.exists(p4c_build_logs):
        print(f"Error: p4c_build_logs executable not found: {p4c_build_logs}")
        return

    p4_files = []
    for root, _, files in os.walk(build_only_dir):
        for file in files:
            if file.endswith("opt.p4"):
                p4_files.append(os.path.join(root, file))

    print(f"Found {len(p4_files)} P4 programs. Running p4c-build-logs with {num_workers} workers...")


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

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            executor.submit(run_single_p4c_build_logs, cmd, p4_file, relative_folder): p4_file
            for cmd, p4_file in zip(commands, p4_files)
        }

        for future in as_completed(futures):
            p4_file = futures[future]
            try:
                result = future.result()
                print(f"{result[0]}: {result[1]}")
            except Exception as e:
                print(f"{p4_file}: failed with exception: {e}")

def rm_files_with_errors(dir):
    """
    Finds all files in the given directory that contain the word 'error' in their log.txt file.
    """
    error_files = []
    for root, _, files in os.walk(dir):
        if "opt.p4" in files:
            log_file_path = os.path.join(root, "log.txt")
            if os.path.exists(log_file_path):
                found_zero_errors = False
                with open(log_file_path, "r") as log_file:
                    found_zero_errors = any(line.startswith("0 errors") for line in log_file)    
                if not found_zero_errors:
                    error_files.append(log_file_path)
                    debug_print(f"Found error in {log_file_path}")                      
            else:
                print(f"Warning: log.txt not found in {root}. Skipping...")
    if error_files:
        print(f"Found {len(error_files)} files with errors:")
        for file in error_files:
            print(file)
            # remove the folder with error
            try:
                shutil.rmtree(os.path.dirname(file))
                print(f"Removed folder {os.path.dirname(file)}")
            except Exception as e:
                print(f"Error removing folder {os.path.dirname(file)}: {e}")
    else:
        print("No files with errors found.")

def main():
    parser = argparse.ArgumentParser(description="Run 'smith' executable multiple times in parallel and store outputs.")
    parser.add_argument("-n", "--num-repetitions", type=int, help="Number of successful repetitions required.")
    parser.add_argument("-e", "--smith-executable", type=str, default="", help="Full path to the 'smith' executable.")
    parser.add_argument("-c", "--p4c-barefoot", type=str, default="", help="Full path to the 'p4c-barefoot' executable.")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of parallel workers (default: 4).")
    parser.add_argument("-b", "--build-only", action="store_true", help="Build all p4 programs in current directory recursively.")
    parser.add_argument("-b-dir", "--build-only-dir", type=str, default="", help="build_p4_programs_recursive")
    parser.add_argument("--p4c-build-logs", type=str, default="", help="Full path to the 'p4c-build-logs' executable.")
    parser.add_argument("--remove-error-programs-dir", type=str, default="", help="Iterate all files found prog with error in log.txt")

    args = parser.parse_args()
    if  args.smith_executable != "" \
        and (os.path.exists(args.smith_executable) or shutil.which(args.smith_executable) is not None) \
        and args.p4c_barefoot != "" and (os.path.exists(args.p4c_barefoot) \
                                         or shutil.which(args.p4c_barefoot) is not None):
        run_smith_parallel(args.num_repetitions, args.smith_executable, args.p4c_barefoot, args.workers)
        return

    if args.build_only and args.build_only_dir != "" and os.path.exists(args.build_only_dir) and args.p4c_barefoot != "":
        build_p4_programs_recursive(args.p4c_barefoot, args.build_only_dir, args.workers)
        return
    
    if args.p4c_build_logs != "" and os.path.exists(args.p4c_build_logs) and args.build_only_dir != "":
        run_p4c_build_logs(args.p4c_build_logs, "smith.tofino/pipe", args.workers, args.build_only_dir)
        return
    
    if args.remove_error_programs_dir != "" and os.path.exists(args.remove_error_programs_dir):
        rm_files_with_errors(args.remove_error_programs_dir)
        return
        
    print("Nothing run, check the arguments")

if __name__ == "__main__":
    main()