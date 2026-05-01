#!/bin/bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo "Setup complete. Now add your API keys to .env file and run: python3 main.py"
