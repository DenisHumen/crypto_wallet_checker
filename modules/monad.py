import requests
from colorama import Fore, Style
import json
import os
import csv
from datetime import datetime
import random
import threading
from tqdm import tqdm
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from rich.console import Console
from contextlib import contextmanager
from itertools import cycle

log_file_path = 'results/logs/log'

# Fixed pyload
pyload1 = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "get_account",
    "params": "0x"
}

@contextmanager
def spinner(message: str = "Processing..."):
    """Displays a spinner with a custom message."""
    console = Console()
    with console.status(f"[bold green]⠴ {message}"):
        yield

def log_error(message):
    with open(log_file_path, 'a') as log_file:
        log_file.write(message + '\n')

def monad_checker(wallet_address, proxy, pyload=pyload1):
    if pyload is not None:
        try:
            url = f'https://layerhub.xyz/be-api/wallets/monad_testnet/{wallet_address}'
            params = {"_rsc": "1bw6b"}
            headers = {
                "accept": "*/*",
                "accept-language": "ru,en-US;q=0.9,en;q=0.8",
                "content-type": "application/json",
                "sec-ch-ua": "\"Not A(Brand\";v=\"8\", \"Chromium\";v=\"132\", \"Google Chrome\";v=\"132\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"Linux\"",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin"
            }

            response = requests.get(url, params=params, headers=headers, proxies={"http": proxy, "https": proxy})
            
            if response.status_code != 200:
                log_error(f'HTTP error: {response.status_code} - {response.text}')
                raise ValueError(f'HTTP error: {response.status_code}')
            
            if not response.content:
                log_error(f'Empty response content - {response.text}')
                raise ValueError('Empty response content')
            
            try:
                data = response.json()
                if isinstance(data, dict) and data.get("message") == "Wallet is not found for chain_id: monad_testnet":
                    log_error(f"Wallet {wallet_address} not found, retrying...")
                    raise ValueError("Wallet not found, retrying...")
                data['wallet_address'] = wallet_address
            except json.JSONDecodeError:
                data = {"wallet_address": wallet_address, "response": response.text}
            
            # Save the result to a JSON file immediately
            file_path = f"results/wallet_json_data/{wallet_address}.json"
            with open(file_path, 'w') as json_file:
                json.dump(data, json_file)
            
            return data
        
        except requests.exceptions.ProxyError as e:
            log_error(f'Proxy {proxy} error: ' + str(e))
            raise e
        except requests.exceptions.RequestException as e:
            log_error('Request error: ' + str(e))
            raise e
        except Exception as e:
            log_error('Error: ' + str(e))
            raise e

    else:
        log_error(f'Error: No pyload found {pyload}')

def process_results(results):
    for result in results:
        wallet_address = result.get('wallet_address', 'unknown_wallet')
        file_path = f"results/wallet_json_data/{wallet_address}.json"
        with open(file_path, 'w') as json_file:
            if isinstance(result, dict):
                json.dump(result, json_file)
            else:
                json_file.write(result)

def process_json_to_csv():
    json_dir = 'results/wallet_json_data'
    csv_file_path = 'results/result.csv'
    wallet_csv_path = 'data/wallet.csv'
    fieldnames = [
        'wallet_address', 'top_percent', 'transaction_count', 'interacted_contracts',
        'wallet_balance', 'active_days', 'active_weeks', 'active_months', 'last_updated',
        'one_million_nads'
    ]

    # Read wallet addresses from data/wallet.csv
    with open(wallet_csv_path, mode='r') as wallet_file:
        reader = csv.reader(wallet_file)
        next(reader)  # Skip header
        wallet_order = [row[0] for row in reader]

    with open(csv_file_path, mode='w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for wallet_address in wallet_order:
            file_path = os.path.join(json_dir, f"{wallet_address}.json")
            if os.path.exists(file_path):
                with open(file_path, 'r') as json_file:
                    data = json.load(json_file)
                    response = json.dumps(data)  # Convert the JSON object back to a string

                    # Extract key data from the response
                    parsed_data = parse_json_response(response)

                    writer.writerow({
                        'wallet_address': data.get('wallet_address', 'unknown_wallet'),
                        'top_percent': parsed_data['top_percent'],
                        'transaction_count': parsed_data['transaction_count'],
                        'interacted_contracts': parsed_data['interacted_contracts'],
                        'wallet_balance': parsed_data['wallet_balance'],
                        'active_days': parsed_data['active_days'],
                        'active_weeks': parsed_data['active_weeks'],
                        'active_months': parsed_data['active_months'],
                        'last_updated': parsed_data['last_updated'],
                        'one_million_nads': parsed_data['one_million_nads']  # Write new field to CSV
                    })

def extract_value(response, key):
    try:
        start = response.index(f'"{key}":') + len(key) + 3
        end = response.index(',', start)
        value = response[start:end].strip()
        if value.startswith(':'):
            value = value[1:].trip()
        if value.endswith('}'):
            value = value[:-1].strip()
        return value
    except ValueError:
        return ''

def extract_value_from_json(response, key):
    try:
        start = response.index(key) + len(key) + 1
        end = response.index(',', start)
        value = response[start:end].strip()
        if value.startswith(':'):
            value = value[1:].strip()
        return value
    except ValueError:
        return ''

def parse_json_response(response):
    try:
        data = json.loads(response)
        top_percent = data['walletPerformance']['topPercent']
        transaction_count = data['widget']['data']['stats'][0]['value']
        interacted_contracts = data['widget']['data']['stats'][1]['value']
        wallet_balance = data['cardsList'][0]['data']['stats'][0]['value']
        active_days = data['cardsList'][1]['data']['activeDays']['value']
        active_weeks = data['cardsList'][1]['data']['activeWeeks']['value']
        active_months = data['cardsList'][1]['data']['activeMonths']['value']
        last_updated = datetime.utcfromtimestamp(data['lastUpdated']).strftime('%Y-%m-%d %H:%M:%S')
        one_million_nads = data['widget']['data']['stats'][2]['value']  # New field
        return {
            'top_percent': top_percent,
            'transaction_count': transaction_count,
            'interacted_contracts': interacted_contracts,
            'wallet_balance': wallet_balance,
            'active_days': active_days,
            'active_weeks': active_weeks,
            'active_months': active_months,
            'last_updated': last_updated,
            'one_million_nads': one_million_nads  # Include new field in the result
        }
    except (KeyError, ValueError, TypeError) as e:
        log_error(f'Error parsing response: {str(e)}')
        return {
            'top_percent': '',
            'transaction_count': '',
            'interacted_contracts': '',
            'wallet_balance': '',
            'active_days': '',
            'active_weeks': '',
            'active_months': '',
            'last_updated': '',
            'one_million_nads': ''  # Default value for new field in case of error
        }

def get_wallets_and_proxies():
    wallets = []
    proxies = []
    with open('data/wallet.csv', mode='r') as file:
        reader = csv.reader(file)
        next(reader)  # Skip header
        for row in reader:
            if len(row) >= 2:
                wallets.append(row[0])
                proxies.append(row[1])
    return wallets, proxies

def get_reserv_proxies():
    reserv_proxies = []
    with open('data/reserv_proxy.csv', mode='r') as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) > 0:
                reserv_proxies.append(row[0])
    return reserv_proxies

def process_wallets(wallets, proxies, reserv_proxies, num_threads, sleep_between_wallet, sleep_between_replace_proxy, limit_replace_proxy):
    results = []
    proxy_pool = iter(proxies)  # Create an iterator for proxies
    spinner_cycle = cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])  # Spinner animation frames

    def process_wallet_task(wallet_address):
        proxy = next(proxy_pool, random.choice(reserv_proxies))  # Get the next proxy or fallback
        attempts = 0
        while attempts < limit_replace_proxy:
            try:
                result = monad_checker(wallet_address, proxy)
                return result, True  # Return result and success status
            except (ValueError, requests.exceptions.RequestException) as e:
                log_error(f"Error processing wallet {wallet_address}: {str(e)}")
                proxy = random.choice(reserv_proxies)  # Replace proxy on failure
                time.sleep(random.uniform(*sleep_between_replace_proxy))
                attempts += 1
        return wallet_address, False  # Return wallet address and failure status

    bar_length = 40  # Length of the progress bar
    total_wallets = len(wallets)
    completed_wallets = 0

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        future_to_wallet = {executor.submit(process_wallet_task, wallet): wallet for wallet in wallets}
        for future in as_completed(future_to_wallet):
            wallet = future_to_wallet[future]
            try:
                result, success = future.result(timeout=10)  # Ensure thread doesn't hang for more than 10 seconds
                if success:
                    results.append(result)
                    status_color = Fore.GREEN
                else:
                    log_error(f"Failed to process wallet: {wallet}")
                    status_color = Fore.RED
            except TimeoutError:
                log_error(f"Timeout error for wallet {wallet}")
                status_color = Fore.RED
            except Exception as e:
                log_error(f"Unhandled exception for wallet {wallet}: {str(e)}")
                status_color = Fore.RED
            finally:
                completed_wallets += 1
                progress = int((completed_wallets / total_wallets) * bar_length)
                bar = "█" * progress + "░" * (bar_length - progress)
                spinner_frame = next(spinner_cycle)  # Get the next frame of the spinner
                print(
                    f"\r[{bar}] {completed_wallets}/{total_wallets} | {spinner_frame} | {status_color}Wallet: {wallet}{Style.RESET_ALL}",
                    end="",
                    flush=True,
                )

    ensure_all_wallets_processed(wallets, proxies, reserv_proxies, results, sleep_between_replace_proxy, limit_replace_proxy)
    print()  # Move to the next line after the progress bar is complete
    return results

def process_wallet(wallet_address, proxy, reserv_proxies, results, sleep_between_replace_proxy, limit_replace_proxy):
    success = False
    attempts = 0
    while not success and attempts < limit_replace_proxy:
        try:
            result = monad_checker(wallet_address, proxy)
            results.append(result)
            success = True
        except ValueError as e:
            log_error(str(e))
            time.sleep(random.uniform(*sleep_between_replace_proxy))
        except requests.exceptions.ProxyError as e:
            log_error(f'Proxy error with proxy {proxy}: ' + str(e))
            time.sleep(random.uniform(*sleep_between_replace_proxy))
            proxy = random.choice(reserv_proxies)
        except requests.exceptions.RequestException as e:
            log_error(f'Request error: ' + str(e))
            time.sleep(random.uniform(*sleep_between_replace_proxy))
        except json.JSONDecodeError as e:
            log_error(f'JSON decode error: ' + str(e))
            time.sleep(random.uniform(*sleep_between_replace_proxy))
        attempts += 1

def ensure_all_wallets_processed(wallets, proxies, reserv_proxies, results, sleep_between_replace_proxy, limit_replace_proxy):
    for wallet_address in wallets:
        file_path = f"results/wallet_json_data/{wallet_address}.json"
        if not os.path.exists(file_path):
            proxy = random.choice(reserv_proxies)
            process_wallet(wallet_address, proxy, reserv_proxies, results, sleep_between_replace_proxy, limit_replace_proxy)