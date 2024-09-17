#!/bin/bash

# Set the directory for the virtual environment
VENV_DIR=".venv"

# Check if the .venv directory exists, if not, create it and set up the virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    python3 -m venv $VENV_DIR
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "requirements.txt not found. Please make sure it is in the current directory."
    exit 1
fi

# Install the requirements if they are not already installed
echo "Installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# Launch the grocery_list_db.py program
if [ ! -f "grocery_list_db.py" ]; then
    echo "grocery_list_db.py not found. Please make sure it is in the current directory."
    exit 1
fi

echo "Launching grocery_list_db.py..."
python grocery_list_db.py

# Deactivate the virtual environment after the script ends
deactivate
