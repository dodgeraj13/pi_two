import requests
import time
import sys
import os
import signal
import subprocess
import shutil
from datetime import datetime
import json
import configparser

# Server URL
SERVER_URL = 'https://test-website-lxsb.onrender.com'

# Global variables to track processes and current mode
current_mode = 1  # Default to MLB mode (1)
current_brightness = 60  # Default brightness
mlb_process = None
music_process = None

def is_process_running(process):
    """Check if a process is still running"""
    if process is None:
        return False
    try:
        return process.poll() is None
    except:
        return False

def start_mlb_scoreboard():
    global mlb_process
    if not is_process_running(mlb_process):
        print('Starting MLB scoreboard...')
        try:
            # Change to the MLB scoreboard directory
            os.chdir('/home/pi_two/mlb-led-scoreboard')
            # Start the MLB scoreboard script
            mlb_process = subprocess.Popen([
                'sudo', './main.py',
                '--led-rows=64',
                '--led-cols=64',
                '--led-gpio-mapping=adafruit-hat-pwm',
                f'--led-brightness={current_brightness}',
                '--led-slowdown-gpio=2'
            ], start_new_session=True)  # Run in new session
            print('MLB scoreboard started')
        except Exception as e:
            print('Error starting MLB scoreboard:', e)
            mlb_process = None

def start_music_display():
    global music_process
    if not is_process_running(music_process):
        print('Starting music display...')
        try:
            # Change to the music display directory
            music_dir = '/home/pi_two/rpi-spotify-matrix-display'
            os.chdir(music_dir)
            print(f'Changed to directory: {os.getcwd()}')
            
            # Check if config file exists
            config_path = os.path.join(music_dir, 'impl', 'config.json')
            print(f'Looking for config file at: {config_path}')
            
            if not os.path.exists(config_path):
                print('Config file not found at:', config_path)
                print('Directory contents:', os.listdir(os.path.join(music_dir, 'impl')))
                print('Please ensure config.json exists in the impl directory')
                return
            
            print('Found config file, starting music display...')
            # Change to the impl directory before starting the script
            os.chdir(os.path.join(music_dir, 'impl'))
            print(f'Changed to impl directory: {os.getcwd()}')
            
            # Create config.ini with emulator settings
            config_ini = os.path.join(os.path.dirname(os.getcwd()), 'config.ini')
            print(f'Creating {config_ini}')
            
            try:
                config = configparser.ConfigParser()
                
                # Matrix section with emulator settings
                config['Matrix'] = {
                    'hardware_mapping': 'adafruit-hat-pwm',
                    'brightness': str(current_brightness),
                    'gpio_slowdown': '2',
                    'limit_refresh_rate_hz': '0',
                    'shutdown_delay': '600'
                }
            
                
                # Write INI config
                with open(config_ini, 'w') as f:
                    config.write(f)
                
                print('Config file created successfully')
            except Exception as e:
                print(f'Error creating config file: {e}')
                return
            
            # Start the music display script
            music_process = subprocess.Popen([
                'sudo', '/home/pi_two/rpi-spotify-matrix-display/.venv/bin/python3',
                'controller_v3.py'  # Use relative path since we're in the impl directory
            ], start_new_session=True)  # Run in new session
            print('Music display started')
        except Exception as e:
            print('Error starting music display:', e)
            music_process = None

def stop_mlb_scoreboard():
    global mlb_process
    if is_process_running(mlb_process):
        print('Stopping MLB scoreboard...')
        try:
            # Send SIGTERM to the process group
            os.killpg(os.getpgid(mlb_process.pid), signal.SIGTERM)
            mlb_process = None
            print('MLB scoreboard stopped')
        except Exception as e:
            print('Error stopping MLB scoreboard:', e)

def stop_music_display():
    global music_process
    if is_process_running(music_process):
        print('Stopping music display...')
        try:
            # Send SIGTERM to the process group
            os.killpg(os.getpgid(music_process.pid), signal.SIGTERM)
            music_process = None
            print('Music display stopped')
        except Exception as e:
            print('Error stopping music display:', e)

def get_state():
    try:
        response = requests.get(f'{SERVER_URL}/state', timeout=2)  # Reduced timeout
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting state: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except requests.exceptions.Timeout:
        print("Request timed out - server might be slow to respond")
        return None
    except requests.exceptions.ConnectionError:
        print("Connection error - server might be down")
        return None
    except Exception as e:
        print(f"Error connecting to server: {e}")
        return None

def handle_mode_change(new_mode):
    global current_mode
    
    if new_mode != current_mode:
        print(f"\n[{datetime.now()}] Switching from mode {current_mode} to {new_mode}")
        
        # Stop all processes first
        stop_mlb_scoreboard()
        stop_music_display()
        
        # Start appropriate process based on new mode
        if new_mode == 1:  # MLB mode
            start_mlb_scoreboard()
        elif new_mode == 2:  # Music mode
            start_music_display()
        else:
            print(f"Unknown mode {new_mode} - no action taken")
        
        current_mode = new_mode
    else:
        print(f"Already in mode {new_mode}, no change needed")

def handle_brightness_change(new_brightness):
    global current_brightness
    
    if new_brightness != current_brightness:
        print(f"\n[{datetime.now()}] Updating brightness from {current_brightness} to {new_brightness}")
        current_brightness = new_brightness
        
        # Update brightness for running processes
        update_running_processes_brightness()
    else:
        print(f"Brightness already at {new_brightness}, no change needed")

def update_running_processes_brightness():
    """Update brightness for currently running processes"""
    # For MLB process, we need to restart it with new brightness
    if is_process_running(mlb_process):
        print("Restarting MLB process with new brightness...")
        stop_mlb_scoreboard()
        start_mlb_scoreboard()
    
    # For music process, we need to restart it with new brightness
    if is_process_running(music_process):
        print("Restarting music process with new brightness...")
        stop_music_display()
        start_music_display()

def main():
    print("Starting LED Controller...")
    print(f"Server URL: {SERVER_URL}")
    print("Checking server status...")
    
    # Test server connection
    test_response = requests.get(f'{SERVER_URL}/state', timeout=2)  # Reduced timeout
    if test_response.status_code == 200:
        print("Server is responding correctly")
    else:
        print(f"Warning: Server returned status code {test_response.status_code}")
        print(f"Response: {test_response.text}")
    
    while True:
        try:
            # Get current state from server
            state = get_state()
            
            if state:
                # Handle mode changes
                if 'mode' in state:
                    handle_mode_change(state['mode'])
                
                # Handle brightness changes
                if 'brightness' in state:
                    handle_brightness_change(state['brightness'])
            else:
                print("No valid state received from server")
            
            # Wait 2 seconds before next check (reduced from 3)
            time.sleep(2)
            
        except KeyboardInterrupt:
            print("\nStopping LED Controller...")
            # Clean up processes before exiting
            stop_mlb_scoreboard()
            stop_music_display()
            sys.exit(0)
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(2)  # Reduced from 3

if __name__ == "__main__":
    main() 