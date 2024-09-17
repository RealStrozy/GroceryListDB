# GroceryListDB

GroceryListDB is a Python-based application for managing grocery inventory and shopping lists. It allows you to maintain an inventory database, create shopping lists, manage default shopping lists, and print lists using a thermal printer. The program also integrates with the upcitemdb.com API to fetch product information using UPC codes.

## Features

- **Inventory Management**: Add and remove items from the inventory, including automatic adjustments of quantities.
- **Default Shopping Lists**: Create, edit, and delete default shopping lists for easy shopping list creation.
- **Shopping List Creation**: Generate shopping lists based on current inventory and default lists.
- **Historical Lists**: Save and reprint historical shopping lists with UUIDs or specific dates.
- **Reports**: Print reports for current inventory and default shopping lists.

## Prerequisites

- **Python 3.x**: Ensure Python 3.x is installed on your system.
- **Required Python Packages**: Install required packages using `pip`:
  ```bash
  pip install -r requirements.txt
  ```
- **Thermal Printer**: An ESC/POS-compatible thermal printer is required for printing functionalities.
- **Database**: The program uses SQLite for inventory and history databases.

## Installation

1. Clone the repository or download the program files.
2. Install the required Python packages using `pip`:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a configuration file (`config.ini`) if it doesn't exist. This file contains printer configurations. The program generates a default configuration file if it's not found.

## Configuration

The program uses a configuration file (`config.ini`) to set up the printer. If the configuration file is not present, a default one is created with the following parameters:

```ini
[Printer]
idVendor = 0x0416
idProduct = 0x5011
in_ep = 0x81
out_ep = 0x03
profile = TM-P80
chr_width = 48
```

Modify these values to match your printer's specifications.

## Usage

### Main Menu Options

1. **Add items to inventory**: Add items to your inventory manually or by scanning UPCs.
2. **Remove items from inventory**: Remove items or adjust quantities in the inventory.
3. **Create shopping list**: Create a shopping list based on default lists and current inventory.
4. **Set up default shopping lists**: Manage default shopping lists (add, edit, delete).
5. **Historical shopping lists**: View and reprint historical shopping lists using dates or UUIDs.
6. **Reports**: Print reports for inventory and default lists.
7. **Print test page**: Print a test page to verify printer setup.
8. **Exit**: Exit the application.

### Printer Setup

Ensure that your printer is connected and configured according to the details in the `config.ini` file. The printer should be ESC/POS-compatible.

### Database Management

The program uses SQLite databases stored in the `./.data` directory:

- **`current.db`**: Stores current inventory and default shopping lists.
- **`history.db`**: Stores historical shopping lists.

The program creates these databases and required tables if they do not exist.

## Key Functions

### Inventory Management

- **Adding Items**: Use `user_items_to_inventory` to add items to the inventory manually or via UPC.
- **Removing Items**: Use `user_items_from_inventory` to remove or adjust item quantities.

### Default Shopping Lists

- **Creating**: Use `add_default_shopping_list` to create new default shopping lists.
- **Editing**: Use `edit_default_shopping_list` to add or remove items from existing lists.
- **Deleting**: Use `delete_default_shopping_list` to remove lists and associated items.

### Shopping List Creation

- **Create List**: Use `create_shopping_list` to generate a shopping list by comparing default lists with current inventory.
- **Print List**: Use `print_shopping_list` to print the created shopping list with optional barcode.

### Reports

- **Inventory Report**: Print a report of the current inventory using `inventory_report`.
- **Default Lists Report**: Print all default shopping lists using `print_all_default_lists`.

### Historical Lists

- **View and Reprint**: Use `print_historical_list` to view and print historical lists based on a date or UUID.

## Error Handling and Validation

The program includes error handling for database operations, API requests, and user inputs. For example:
- **Database Integrity**: Handles duplicate entries and constraints.
- **API Requests**: Checks for HTTP errors when fetching data using UPC codes.
- **User Input**: Validates user input, including UPC codes and menu selections.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or report issues.
