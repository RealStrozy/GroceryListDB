import configparser
import time
import uuid
import sqlite3
import requests
from datetime import datetime, timezone
from escpos import printer
import re
import os


class BColors:
    HEADER = '\033[95m'
    OK_BLUE = '\033[94m'
    OK_CYAN = '\033[96m'
    OK_GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    END_C = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def read_config(config_file='config.ini'):
    """
    Reads printer configuration from the config file. If the file or section does not exist, it creates a default config.
    Returns:
        dict: A dictionary of configuration values.
    """
    config = configparser.ConfigParser()
    config.read(config_file)

    try:
        # Extract configuration values
        config_values = {
            'idVendor': config.get('Printer', 'idVendor'),
            'idProduct': config.get('Printer', 'idProduct'),
            'in_ep': config.get('Printer', 'in_ep'),
            'out_ep': config.get('Printer', 'out_ep'),
            'profile': config.get('Printer', 'profile'),
            'chr_width': config.get('Printer', 'chr_width')
        }
    except configparser.NoSectionError:
        # If the section is not found, create a default configuration
        config['Printer'] = {
            'idVendor': '0x0416',
            'idProduct': '0x5011',
            'in_ep': '0x81',
            'out_ep': '0x03',
            'profile': 'TM-P80',
            'chr_width': '48'
        }
        with open(config_file, 'w') as configfile:
            config.write(configfile)
        print(BColors.WARNING + "Please use the config.ini file to configure your printer." + BColors.END_C)
        time.sleep(10)
        exit(1)

    return config_values


def printer_connect(config):
    """
    Connects to the printer using the configuration data.
    Args:
        config (dict): Printer configuration dictionary.
    Returns:
        printer.Usb: The USB printer object.
    """
    return printer.Usb(
        int(config['idVendor'], 16),
        int(config['idProduct'], 16),
        in_ep=int(config['in_ep'], 16),
        out_ep=int(config['out_ep'], 16),
        profile=str(config['profile'])
    )


def check_db(database, tables):
    """
    Checks if the required tables exist in the database, creates them if not.
    Args:
        database (str): Database name.
        tables (list): List of tuples, each containing the table name and its creation query.
    """
    with sqlite3.connect(f'./.data/{database}.db') as db:
        cur = db.cursor()
        for table, creation_query in tables:
            cur.execute(f'CREATE TABLE IF NOT EXISTS {table} ({creation_query})')
        db.commit()


def check_history_db():
    """
    Ensures the history database and required tables exist.
    """
    tables = [
        ('lists',
         'ID INTEGER PRIMARY KEY AUTOINCREMENT, UUID TEXT UNIQUE NOT NULL, creation_time INTEGER UNIQUE NOT NULL'),
        ('lists_items',
         'ID INTEGER PRIMARY KEY AUTOINCREMENT, default_lists_id INTEGER, name TEXT NOT NULL, qty INTEGER NOT NULL,'
         'FOREIGN KEY (default_lists_id) REFERENCES lists(UUID)')
    ]
    check_db('history', tables)


def check_current_db():
    """
    Ensures the current database and required tables exist.
    """
    tables = [
        ('inventory',
         'ID INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, upc INTEGER UNIQUE NOT NULL, qty INTEGER NOT NULL,'
         'description TEXT, time_first_added INTEGER, category TEXT'),
        ('default_lists',
         'ID INTEGER PRIMARY KEY AUTOINCREMENT, UUID TEXT UNIQUE NOT NULL, name TEXT UNIQUE NOT NULL'),
        ('default_lists_items',
         'ID INTEGER PRIMARY KEY AUTOINCREMENT, default_lists_id INTEGER, name TEXT NOT NULL, '
         'upc INTEGER UNIQUE NOT NULL, qty INTEGER NOT NULL, description TEXT, time_first_added INTEGER, category TEXT,'
         'FOREIGN KEY (default_lists_id) REFERENCES default_lists(ID)')
    ]
    check_db('current', tables)


def search_db(database, db_table, term=None, value=None):
    """
    Searches for records in the database table.
    Args:
        database (str): Database name.
        db_table (str): Table name.
        term (str, optional): Column name to search in. Defaults to None.
        value (str, optional): Value to match in the column. Defaults to None.
    Returns:
        list: List of matching rows.
    """
    with sqlite3.connect(f'./.data/{database}.db') as db:
        cur = db.cursor()
        if term and value:
            query = f'SELECT * FROM {db_table} WHERE {term} = ?'
            cur.execute(query, (value,))
        else:
            query = f'SELECT * FROM {db_table}'
            cur.execute(query)
        return cur.fetchall()


def add_remove_db(database, db_table, add=True, **kwargs):
    """
    Adds or removes records from the database table.
    Args:
        database (str): Database name.
        db_table (str): Table name.
        add (bool, optional): True to add, False to remove. Defaults to True.
        **kwargs: Column-value pairs for the database operation.
    """
    with sqlite3.connect(f'./.data/{database}.db') as db:
        cur = db.cursor()
        if add:
            try:
                columns = ', '.join(kwargs.keys())
                placeholders = ', '.join(['?'] * len(kwargs))
                query = f'INSERT INTO {db_table} ({columns}) VALUES ({placeholders})'
                cur.execute(query, tuple(kwargs.values()))
                db.commit()
            except sqlite3.IntegrityError:
                print('Already in database.')
        else:
            if 'id' in kwargs:
                query = f'DELETE FROM {db_table} WHERE ID = ?'
                cur.execute(query, (kwargs['id'],))
                db.commit()
            else:
                print('Can only delete if database ID is known.')


def mod_qty_db(database, db_table, db_id, mod=1, add=True):
    """
    Modifies the quantity of an item in the database.
    Args:
        database (str): Database name.
        db_table (str): Table name.
        db_id (int): ID of the item to modify.
        mod (int, optional): Amount to modify by. Defaults to 1.
        add (bool, optional): True to add, False to subtract. Defaults to True.
    """
    operation = '+' if add else '-'
    with sqlite3.connect(f'./.data/{database}.db') as db:
        cur = db.cursor()
        query = f'UPDATE {db_table} SET qty = qty {operation} ? WHERE ID = ?'
        cur.execute(query, (mod, db_id))
        db.commit()


def fetch_info(upc):
    """
    Fetches product information from an external API using UPC.
    Args:
        upc (str): The UPC code to search for.
    Returns:
        tuple: A tuple containing the product information, rate limit remaining, and reset time.
    """
    url = f'https://api.upcitemdb.com/prod/trial/lookup?upc={upc}'
    response = requests.get(url)

    try:
        response.raise_for_status()
        upc_data = response.json()
        rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', 'N/A')
        rate_limit_reset = response.headers.get('X-RateLimit-Reset', 'N/A')

        if upc_data['items']:
            return upc_data['items'], rate_limit_remaining, rate_limit_reset
        else:
            return False, rate_limit_remaining, rate_limit_reset
    except requests.exceptions.HTTPError:
        return False, '', ''


def get_item_info_by_upc():
    """
    Prompts the user for a UPC, checks inventory, and fetches from an external API if needed.
    Returns:
        tuple: A tuple (item_name, description, category, upc) or None if the user decides to go back.
    """
    while True:
        upc = input("Enter item UPC (0 to go back): ")
        if upc == '0':
            return None

        # Check inventory
        inventory_item = search_db('current', 'inventory', 'upc', upc)
        if inventory_item:
            item_name, description, category = inventory_item[0][1], inventory_item[0][4], inventory_item[0][6]
            print(f"Item '{item_name}' found in inventory.")
            return item_name, description, category, upc

        # Fetch information from the API
        fetch, remaining, reset = fetch_info(upc)
        if remaining and reset:
            until = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(int(reset)))
            print(f"You have {remaining} search(es) remaining until {until}.")

        if fetch:
            product_info = fetch[0]
            item_name = product_info.get('title', 'Unknown')
            description = product_info.get('description', 'No description available')
            category = product_info.get('category', 'Uncategorized')
            print(f"Item '{item_name}' found via API.")
            return item_name, description, category, upc

        # Prompt user for item information if not found in API
        item_name = input(f'{BColors.WARNING}Enter product name (0 to go back): {BColors.END_C}')
        if item_name == '0':
            continue

        description = input("Enter description: ")
        category = input("Enter category: ")

        return item_name, description, category, upc


def user_items_to_inventory():
    """
    Allows the user to add items to the inventory.
    """
    check_current_db()

    while True:
        print('Add item: ')
        upc = input('Enter UPC (0 for exit): ')
        if upc == '0':
            return

        # Check if item is in inventory
        search = search_db('current', 'inventory', 'upc', upc)
        if search:
            mod_qty_db('current', 'inventory', search[0][0], 1)
            print(search[0][1])
        else:
            fetch, remaining, reset = fetch_info(upc)
            if remaining and reset:
                until = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(int(reset)))
                print(f'You have {remaining} search(s) until {until}')

            if fetch:
                print(fetch[0]['title'])
                product_info = fetch[0]
                new_item = {
                    'name': product_info['title'],
                    'upc': upc,
                    'qty': 1,
                    'description': product_info['description'],
                    'time_first_added': int(time.time())
                }
            else:
                while True:
                    item_name = input(f'{BColors.WARNING}Enter product name (0 for exit): {BColors.END_C}')
                    if item_name == '0':
                        return
                    # Check if the name is only numbers
                    if item_name.isdigit():
                        print(
                            f"{BColors.FAIL}Invalid name. Please enter a name that is not just numbers.{BColors.END_C}")
                    else:
                        break

                description = input("Enter description: ")
                new_item = {
                    'name': item_name,
                    'upc': upc,
                    'qty': 1,
                    'description': description,
                    'time_first_added': int(time.time())
                }

            add_remove_db('current', 'inventory', add=True, **new_item)
            print(f"Item '{new_item['name']}' has been added to the inventory.")


def user_items_from_inventory():
    """
    Allows the user to remove items from the inventory.
    """
    check_current_db()

    while True:
        print('Remove item: ')
        upc = input('Enter UPC (0 for exit): ')
        if upc == '0':
            return

        # Check if item is in inventory
        search = search_db('current', 'inventory', 'upc', upc)
        if search:
            if search[0][3] > 0:
                mod_qty_db('current', 'inventory', search[0][0], add=False)
                print(search[0][1])
            else:
                print(f'{BColors.WARNING}{search[0][1]} has 0 in inventory already.{BColors.END_C}')
        else:
            print(f'{BColors.WARNING}Item is not currently in inventory.{BColors.END_C}')


def add_default_shopping_list(list_name):
    """
    Adds a new default shopping list.
    Args:
        list_name (str): The name of the new shopping list.
    """
    check_current_db()

    if search_db('current', 'default_lists', 'name', list_name):
        print(f"The shopping list '{list_name}' already exists.")
        return

    new_list = {
        'UUID': str(uuid.uuid4()),
        'name': list_name
    }
    add_remove_db('current', 'default_lists', add=True, **new_list)
    print(f"Shopping list '{list_name}' has been added.")


def edit_default_shopping_list():
    """
    Edits an existing default shopping list by adding or removing items.
    """
    shopping_lists = search_db('current', 'default_lists')
    if not shopping_lists:
        print("No default shopping lists found.")
        return

    print("Default Shopping Lists:")
    for idx, shopping_list in enumerate(shopping_lists, start=1):
        print(f"{idx}. {shopping_list[2]}")  # Display list name

    try:
        selection = int(input("Select a shopping list to edit (0 to exit): "))
    except ValueError:
        print("Invalid input.")
        return

    if selection == 0:
        return

    list_id = shopping_lists[selection - 1][0]

    while True:
        action = input("Enter 'add'(1) to add or change items, 'remove' to remove items, 'exit'(0) to finish: ").strip().lower()
        if action == 'exit' or action == '0':
            break
        elif action not in ('add', 'remove', '1'):
            print("Invalid action.")
            continue

        while True:
            if action == 'add' or action == '1':
                item_info = get_item_info_by_upc()
                if not item_info:
                    break

                item_name, description, category, upc = item_info

                # Check if the item is already on the list
                existing_items = search_db('current', 'default_lists_items', 'upc', upc)
                existing_item = next((item for item in existing_items if item[1] == list_id), None)

                if existing_item:
                    print(f"Item '{item_name}' is already on the list.")
                    try:
                        mod_qty = int(input("Enter quantity to modify: "))
                    except ValueError:
                        print("Invalid input.")
                        continue

                    # Modify the quantity using the mod_qty_db function
                    mod_qty_db('current', 'default_lists_items',
                               existing_item[0], mod=(mod_qty - existing_item[4]))
                    print(f"Item '{item_name}' quantity modified.")

                else:
                    try:
                        qty = int(input("Enter quantity: "))
                    except ValueError:
                        print("Invalid input.")
                        continue

                    new_item = {
                        'default_lists_id': list_id,
                        'name': item_name,
                        'upc': upc,
                        'qty': qty,
                        'description': description,
                        'time_first_added': int(time.time()),
                        'category': category
                    }
                    add_remove_db('current', 'default_lists_items', add=True, **new_item)
                    print(f"Item '{item_name}' added to shopping list.")

            elif action == 'remove':
                upc = input("Enter the UPC of the item to remove (0 to go back): ")
                if upc == '0':
                    break

                items = search_db('current', 'default_lists_items', 'upc', upc)
                if not items:
                    print("Item not found in the list.")
                    continue

                item_id = items[0][0]
                add_remove_db('current', 'default_lists_items', add=False, id=item_id)
                print("Item removed from the list.")


def delete_default_shopping_list(list_name):
    """
    Deletes an existing default shopping list and associated items.
    Args:
        list_name (str): The name of the shopping list to delete.
    """
    check_current_db()
    shopping_list = search_db('current', 'default_lists', 'name', list_name)

    if not shopping_list:
        print(f"The shopping list '{list_name}' does not exist.")
        return

    list_id = shopping_list[0][0]
    add_remove_db('current', 'default_lists', add=False, id=list_id)
    print(f"Shopping list '{list_name}' has been deleted.")

    # Clean up related items in default_lists_items
    with sqlite3.connect(f'./.data/current.db') as db:
        cur = db.cursor()
        cur.execute('DELETE FROM default_lists_items WHERE default_lists_id = ?', (list_id,))
        db.commit()
        print(f"Items associated with '{list_name}' have been deleted.")


def remove_item_permanently():
    """
    Allows the user to permanently remove an item from the inventory.
    The user can select an item from a list or input a UPC directly.
    """
    # Ensure the current database and tables exist
    check_current_db()

    # Ask the user how they want to find the item
    print("Choose how you want to find the item to remove:")
    print("1. Select from a list")
    print("2. Enter a UPC")

    try:
        method_choice = int(input("Enter your choice (1 or 2): "))

        # Option 1: Select from a list
        if method_choice == 1:
            # Fetch all items in the inventory
            items = search_db('current', 'inventory')

            if not items:
                print("The inventory is empty.")
                return

            # Display all items by name
            print("Select an item to remove:")
            for idx, item in enumerate(items, start=1):
                print(f"{idx}. {item[1]} ({item[2]})")  # Display the item name

            # Prompt the user to select an item to remove
            selection = int(input("Enter the number of the item to remove (0 to cancel): "))

            if selection == 0:
                print("Operation canceled.")
                return

            # Validate the selection
            if 1 <= selection <= len(items):
                item_id = items[selection - 1][0]  # Get the ID of the selected item
                item_name = items[selection - 1][1]  # Get the name of the selected item
            else:
                print("Invalid selection. Please select a valid item number.")
                return

        # Option 2: Enter a UPC
        elif method_choice == 2:
            # Prompt the user to enter the UPC
            upc = input("Enter the UPC of the item to remove: ")

            # Check if item is in inventory
            search = search_db('current', 'inventory', 'upc', upc)
            if not search:
                print(f"Item with UPC {upc} not found in the inventory.")
                return

            item_id = search[0][0]  # Get the ID of the selected item
            item_name = search[0][1]  # Get the name of the selected item

        else:
            print("Invalid choice. Please select 1 or 2.")
            return

        # Confirm removal
        confirm = input(f"Are you sure you want to permanently remove '{item_name}'? (yes/no): ").strip().lower()
        if confirm == 'yes':
            # Remove the item using add_remove_db
            add_remove_db('current', 'inventory', add=False, id=item_id)
            print(f"Item '{item_name}' has been permanently removed.")
        else:
            print("Operation canceled.")

    except ValueError:
        print("Invalid input. Please enter a number.")



def edit_inventory_item():
    """
    Allows the user to edit the name and description of an item in the inventory.
    The user can select an item from a list or input a UPC directly.
    """
    # Ensure the current database and tables exist
    check_current_db()

    # Ask the user how they want to find the item
    print("Choose how you want to find the item to edit:")
    print("1. Select from a list")
    print("2. Enter a UPC")

    try:
        method_choice = int(input("Enter your choice (1 or 2): "))

        # Option 1: Select from a list
        if method_choice == 1:
            # Fetch all items in the inventory
            items = search_db('current', 'inventory')

            if not items:
                print("The inventory is empty.")
                return

            # Display all items by name
            print("Select an item to edit:")
            for idx, item in enumerate(items, start=1):
                print(f"{idx}. {item[1]} ({item[2]})")  # Display the item name and description

            # Prompt the user to select an item to edit
            selection = int(input("Enter the number of the item to edit (0 to cancel): "))

            if selection == 0:
                print("Operation canceled.")
                return

            # Validate the selection
            if 1 <= selection <= len(items):
                item_id = items[selection - 1][0]  # Get the ID of the selected item
                current_name = items[selection - 1][1]  # Current name of the selected item
                current_description = items[selection - 1][4]  # Current description
            else:
                print("Invalid selection. Please select a valid item number.")
                return

        # Option 2: Enter a UPC
        elif method_choice == 2:
            # Prompt the user to enter the UPC
            upc = input("Enter the UPC of the item to edit: ")

            # Check if item is in inventory
            search = search_db('current', 'inventory', 'upc', upc)
            if not search:
                print(f"Item with UPC {upc} not found in the inventory.")
                return

            item_id = search[0][0]  # Get the ID of the selected item
            current_name = search[0][1]  # Current name of the selected item
            current_description = search[0][4]  # Current description

        else:
            print("Invalid choice. Please select 1 or 2.")
            return

        # Edit item name
        while True:
            new_name = input(f"Enter new name for '{current_name}' (or press Enter to keep current name): ").strip()
            if new_name == "":
                new_name = current_name  # Keep the current name if the user doesn't enter a new one
                break
            elif new_name.isdigit():
                print(f"{BColors.FAIL}Invalid name. Please enter a name that is not just numbers.{BColors.END_C}")
            else:
                break

        # Edit item description
        new_description = input(f"Enter new description for '{current_name}' (or press Enter to keep current description): ").strip()
        if new_description == "":
            new_description = current_description  # Keep the current description if the user doesn't enter a new one

        # Update the item in the database
        with sqlite3.connect(f'./.data/current.db') as db:
            cur = db.cursor()
            cur.execute('UPDATE inventory SET name = ?, description = ? WHERE ID = ?', (new_name, new_description, item_id))
            db.commit()
            print(f"Item '{current_name}' has been updated to '{new_name}' with the new description.")

    except ValueError:
        print("Invalid input. Please enter a valid number.")



def print_pdf417(content, width=2, rows=0, height_multiplier=0, data_column_count=0, ec=20, options=0):
    """
    Generate and send a PDF417 barcode command sequence to the printer.
    Args:
        content (str): Content to encode in the barcode.
        width (int, optional): Module width. Defaults to 2.
        rows (int, optional): Number of rows. Defaults to 0.
        height_multiplier (int, optional): Height multiplier. Defaults to 0.
        data_column_count (int, optional): Data column count. Defaults to 0.
        ec (int, optional): Error correction level. Defaults to 20.
        options (int, optional): Barcode options (0 = standard, 1 = truncated). Defaults to 0.
    Returns:
        str: Error message if any issue, else None.
    """

    def validate_parameters():
        if len(content) + 3 >= 500:
            return 'TOO LARGE'
        if not 2 <= width <= 8:
            return 'Width must be between 2 and 8'
        if rows != 0 and not 3 <= rows <= 90:
            return "Rows must be 0 (auto) or between 3 and 90"
        if not 0 <= height_multiplier <= 16:
            return 'Height multiplier must be between 0 and 16'
        if not 0 <= data_column_count <= 30:
            return 'Data column count must be between 0 and 30'
        if not 1 <= ec <= 40:
            return 'Error correction level must be between 1 and 40'
        if options not in [0, 1]:
            return 'Options must be 0 (standard) or 1 (truncated)'
        return None

    error = validate_parameters()
    if error:
        return error

    content = content.encode('utf-8')

    def prefix():
        # Create a byte array for the prefix command sequence (includes pl and ph for one byte settings)
        trunk = bytearray(b'\x1d\x28\x6b\x03\x00\x30')
        return trunk

    def prefix_short():
        # Create a shorter byte array for prefix (without pl and ph)
        trunk = bytearray(b'\x1d\x28\x6b')
        return trunk

    def calculate_pl_ph(measure):
        # Calculate pl and ph based on the length of the content
        total_length = len(measure) + 3  # Length includes 3 additional bytes
        pl = total_length % 256  # Lower byte
        ph = total_length // 256  # Higher byte
        if not ph:
            ph = 0
        pl_ph = pl, ph
        bytearray(pl_ph)
        return pl_ph

    # Start creating the command sequence
    # Select alignment mode centered
    data = bytearray(b'\x1b\x61\x01')
    # Select model: standard or truncated
    data.extend(prefix())
    code_byte = 70
    data.extend(code_byte.to_bytes())
    data.extend(options.to_bytes())

    # Column count
    data.extend(prefix())
    code_byte = 65
    data.extend(code_byte.to_bytes())
    data.extend(data_column_count.to_bytes())

    # Rows count
    data.extend(prefix())
    code_byte = 66
    data.extend(code_byte.to_bytes())
    data.extend(rows.to_bytes())

    # Set dot sizes
    data.extend(prefix())
    code_byte = 67
    data.extend(code_byte.to_bytes())
    data.extend(width.to_bytes())
    data.extend(prefix())
    code_byte = 68
    data.extend(code_byte.to_bytes())
    data.extend(height_multiplier.to_bytes())

    # Set error correction ratio
    data.extend(prefix_short())
    data.extend(bytearray(b'\x04\x00\x30'))
    code_byte = 69
    data.extend(code_byte.to_bytes())
    code_byte = 49
    data.extend(code_byte.to_bytes())
    data.extend(ec.to_bytes())

    # Save is symbol storage area & print from symbol storage area
    data.extend(prefix_short())
    data.extend(calculate_pl_ph(content))  # Calculate and add pl and ph
    data.extend(bytearray(b'\x30\x50\x30'))
    data.extend(content)  # Add the barcode content
    data.extend(prefix())
    code_byte = 81
    data.extend(code_byte.to_bytes())
    data.extend(bytearray(b'\x30'))  # End of sequence generation

    # Sends the sequence to the printer
    p._raw(data)  # noqa

def print_header():
    """
    Prints the header including the logo and current date/time.
    """
    p.hw('INIT')
    p.image('./assets/logo.png', center=True)
    p.hw('INIT')
    p.ln(2)
    now = datetime.now(timezone.utc).strftime('%m/%d/%Y %H:%M:%S %Z')
    p.text(f'Printed at: {now}')


def print_line():
    """
    Prints a horizontal line across the width of the printer.
    """
    line = '-' * int(printer_config['chr_width'])
    p.text(line)


def r_l_justify(str_a, str_b, space_chr=' '):
    """
    Prints two strings where one is justified to the left and one to the right.
    Args:
        str_a (str): Left-justified string.
        str_b (str): Right-justified string.
        space_chr (str, optional): Character to use for spacing. Defaults to 'space'.
    """
    if not space_chr or len(space_chr) != 1:
        p.text('SPACE_CHR must be a single character')
        return

    both_length = len(str_a) + len(str_b)
    if both_length > int(printer_config['chr_width']):
        amt_to_trim = int(printer_config['chr_width']) - (len(str_b) + 5)
        str_a = str_a[:amt_to_trim] + '...'
        both_length = len(str_a) + len(str_b)

    spaces = space_chr * (int(printer_config['chr_width']) - both_length)
    final_str = f"{str_a}{spaces}{str_b}"
    p.hw('INIT')
    p.text(final_str)


def print_list(items, list_uuid=None, barcode=True):
    """
    Prints a shopping list with the given data.
    Args:
        items (list): List of tuples (name, qty).
        list_uuid (str, optional): UUID of the list. Generates if not provided.
        barcode (bool, optional): Whether to print a barcode. Defaults to True.
    Returns:
        dict: Dictionary containing 'time_generated' and 'uuid'.
    """
    list_uuid = list_uuid or str(uuid.uuid4())
    creation_time = int(time.time())

    for item_name, qty in items:
        r_l_justify(str(item_name), str(qty))
    p.ln(1)

    if barcode:
        print_pdf417(list_uuid, width=3)

    return {'time_generated': creation_time, 'uuid': list_uuid}, items


def inventory_report():
    """
    Generates and prints the inventory report.
    """
    items = [(item[1], item[3]) for item in search_db('current', 'inventory')]

    print_header()
    p.ln(2)
    p.set(double_height=True, double_width=True, align='center')
    p.text('Inventory Report')
    p.ln(2)
    p.hw('INIT')
    print_list(items, barcode=False)
    p.cut()


def compare_default_list_to_inventory(default_list_id):
    """
    Compares the default shopping list to current inventory and determines which items need to be added.
    Args:
        default_list_id (int): ID of the default list to compare.
    Returns:
        list: List of tuples (item_name, qty_needed) to add.
    """
    check_current_db()

    default_list_items = search_db('current', 'default_lists_items', 'default_lists_id', default_list_id)
    if not default_list_items:
        print(f"No items found on list searched.")
        return []

    inventory_items = search_db('current', 'inventory')
    inventory_dict = {item[1]: item for item in inventory_items}

    items_to_add = []
    for item in default_list_items:
        default_name, default_qty = item[2], item[4]
        inventory_qty = inventory_dict.get(default_name, (None, None, None, 0))[3]

        if inventory_qty < default_qty:
            items_to_add.append((default_name, default_qty - inventory_qty))

    return items_to_add


def create_shopping_list():
    """
    Creates a shopping list based on a default list and current inventory.
    Returns:
        list: List of items and quantities needed.
    """
    check_current_db()

    shopping_lists = search_db('current', 'default_lists')
    if not shopping_lists:
        print("No default shopping lists available.")
        return []

    print("Default Shopping Lists:")
    for idx, shopping_list in enumerate(shopping_lists, start=1):
        print(f"{idx}. {shopping_list[2]}")

    try:
        selection = int(input("Select a default shopping list to create (0 to exit): "))
    except ValueError:
        print("Invalid input.")
        return []

    if selection == 0:
        return []

    selected_list_id = shopping_lists[selection - 1][0]
    items_needed = compare_default_list_to_inventory(selected_list_id)
    print(f"Initial items needed: {items_needed}")

    additional_items = []
    while True:
        action = input('Would you like to manually add more items? (yes/no): ').strip().lower()
        if action == 'no':
            break
        elif action == 'yes':
            item_info = get_item_info_by_upc()
            if not item_info:
                break

            item_name, description, category, upc = item_info
            try:
                qty = int(input("Enter quantity: "))
            except ValueError:
                print("Invalid input.")
                continue

            additional_items.append((item_name, qty))

    additional_items_to_add = []
    for item_name, qty in additional_items:
        inventory_qty = search_db('current', 'inventory', 'name', item_name)[0][3]
        if inventory_qty < qty:
            additional_items_to_add.append((item_name, qty - inventory_qty))

    combined_items_needed = items_needed + additional_items_to_add
    print(f"Final list of items needed: {combined_items_needed}\n")
    return combined_items_needed


def print_shopping_list(items):
    """
    Prints a shopping list and records it in the history database.
    Args:
        items (list): List of items to be printed.
    """
    if not items:
        return

    check_history_db()

    print_header()
    p.ln(2)
    p.set(double_height=True, double_width=True, align='center')
    p.text('Shopping list')
    p.ln(2)
    p.hw('INIT')

    output, items = print_list(items)
    creation_time, list_uuid = output['time_generated'], str(output['uuid'])
    p.cut()

    add_remove_db('history', 'lists', add=True, UUID=list_uuid, creation_time=creation_time)

    for item_name, qty in items:
        try:
            add_remove_db(
                database='history',
                db_table='lists_items',
                add=True,
                default_lists_id=list_uuid,
                name=item_name,
                qty=qty
            )
        except Exception as e:
            print(f"Error adding item '{item_name}' to history database: {e}")



def print_historical_list():
    """
    Prints historical shopping lists based on a date or UUID provided by the user.
    """
    check_history_db()

    # Prompt user for input (UUID or date)
    search_input = input("Enter the date (YYYY-MM-DD) or UUID to search for historical lists: ").strip()

    # Regular expression pattern to match a UUID format
    uuid_pattern = re.compile(r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$')

    # Initialize variables for the search
    lists = [] # noqa

    # Determine if input is a UUID or a date
    if uuid_pattern.match(search_input):
        # Input is a UUID
        uuid_to_search = search_input

        # Query the database by UUID
        with sqlite3.connect('./.data/history.db') as db:
            cur = db.cursor()
            query = '''
                SELECT UUID, creation_time FROM lists
                WHERE UUID = ?
            '''
            cur.execute(query, (uuid_to_search,))
            lists = cur.fetchall()

    else:
        # Input is not a UUID, try to parse as a date
        try:
            # Convert date_str to a time range in UNIX time
            date_start = datetime.strptime(search_input, "%Y-%m-%d")
            unix_start = int(date_start.replace(tzinfo=timezone.utc).timestamp())
            unix_end = unix_start + 86400  # Adds one day worth of seconds (86400) to get the end of the day

            # Query the database by date range
            with sqlite3.connect('./.data/history.db') as db:
                cur = db.cursor()
                query = '''
                    SELECT UUID, creation_time FROM lists
                    WHERE creation_time BETWEEN ? AND ?
                '''
                cur.execute(query, (unix_start, unix_end))
                lists = cur.fetchall()

        except ValueError:
            # If parsing as a date fails, it's an invalid input
            print("Invalid input. Please enter a valid UUID or date in YYYY-MM-DD format.")
            return

    if not lists:
        print("No historical lists found for the specified input.")
        return

    # For each list, fetch the items and print the list
    for list_uuid, creation_time in lists:
        # Convert creation_time to a formatted date string
        created_date = time.strftime('%Y-%m-%d %H:%M:%S (UTC)', time.gmtime(creation_time))

        # Retrieve the items for this list
        with sqlite3.connect('./.data/history.db') as db:
            cur = db.cursor()
            query = '''
                SELECT name, qty FROM lists_items
                WHERE default_lists_id = ?
            '''
            cur.execute(query, (list_uuid,))
            items = cur.fetchall()

        # Print the historical list using the prepared format
        print_header()
        p.ln(2)
        p.set(double_height=True, double_width=True, align='center', invert=True)
        p.text(f'REPRINT\n{created_date}')
        p.ln(2)
        p.set(invert=False)
        p.text('Shopping List')
        p.ln(2)
        p.hw('INIT')
        print_list(items, list_uuid=list_uuid)
        p.cut()


def print_all_default_lists():
    """
    Retrieves all default shopping lists with their items and quantities and prints it.
    Returns:
        list: A list of lists containing tuples for each default list.
              Each tuple contains (item_name, quantity).
    """
    check_current_db()  # Ensure the database and tables exist

    # This will store the final result
    all_lists_with_items = []

    # Connect to the 'current.db' database
    with sqlite3.connect('./.data/current.db') as db:
        cur = db.cursor()

        # First, fetch all default lists
        cur.execute('SELECT ID, name FROM default_lists')
        default_lists = cur.fetchall()

        # For each default list, fetch the associated items
        for list_id, list_name in default_lists:
            # Retrieve all items for this list
            cur.execute('''
                SELECT name, qty
                FROM default_lists_items
                WHERE default_lists_id = ?
            ''', (list_id,))
            items = cur.fetchall()  # This will be a list of tuples (item_name, quantity)

            # Append the list name and its items to the final result
            all_lists_with_items.append((list_name, items))

            # Prints list
            print_header()
            p.ln(2)
            p.set(double_height=True, double_width=True, align='center', invert=True)
            p.text(f'DEFAULT LIST')
            p.ln(2)
            p.set(double_height=True, double_width=True, align='center', invert=False)
            p.text(list_name)
            p.ln(2)
            p.hw('INIT')
            print_list(items, barcode=False)
            p.cut()

    return all_lists_with_items


def reports_menu():
    """
    Displays the reports menu and handles user choices.
    """
    while True:
        print(f"{BColors.HEADER}Reports{BColors.END_C}")
        print('1. Inventory Report')
        print('2. Default Lists Report')
        print('0. Return to Main Menu')

        choice = input('Enter your choice: ')

        if choice == '0':
            break
        elif choice == '1':
            inventory_report()
        elif choice == '2':
            print_all_default_lists()
        else:
            print('Invalid choice. Please select a valid option.')


def default_shopping_list_menu():
    """
    Displays the default shopping list management menu and handles user choices.
    """
    while True:
        print(f"{BColors.HEADER}Default Shopping List Management{BColors.END_C}")
        print('1. Add a new default shopping list')
        print('2. Edit an existing default shopping list')
        print('3. Delete a default shopping list')
        print('0. Return to main menu')

        choice = input('Enter your choice: ')

        if choice == '0':
            break
        elif choice == '1':
            list_name = input('Enter the name of the new shopping list: ')
            add_default_shopping_list(list_name)
        elif choice == '2':
            edit_default_shopping_list()
        elif choice == '3':
            list_name = input('Enter the name of the shopping list to delete: ')
            delete_default_shopping_list(list_name)
        else:
            print('Invalid choice. Please select a valid option.')


def admin_menu():
    print(f"{BColors.HEADER}Administrator Options{BColors.END_C}")
    print('1. Edit items')
    print('"del". Remove items from inventory database table')
    print('0. Main menu')

    choice = input('Enter your choice: ')

    if choice == '0':
        quit(0)
    elif choice == '1':
        edit_inventory_item()
    elif choice == 'del':
        remove_item_permanently()

    else:
        print('Invalid choice. Please select a valid option.')


def main_menu():
    """
    Displays the main menu and handles user choices.
    """
    while True:
        print(f"{BColors.HEADER}GroceryListDB{BColors.END_C}")
        print('1. Add items to inventory')
        print('2. Remove items from inventory')
        print('3. Create shopping list')
        print('4. Set up default shopping lists')
        print('5. Historical shopping lists')
        print('6. Reports')
        print('7. Administrator Options')
        print('0. Exit')

        choice = input('Enter your choice: ')

        if choice == '0':
            quit(0)
        elif choice == '1':
            user_items_to_inventory()
        elif choice == '2':
            user_items_from_inventory()
        elif choice == '3':
            print_shopping_list(create_shopping_list())
        elif choice == '4':
            default_shopping_list_menu()
        elif choice == '5':
            print_historical_list()
        elif choice == '6':
            reports_menu()
        elif choice == '7':
            admin_menu()
        else:
            print('Invalid choice. Please select a valid option.')


if __name__ == "__main__":
    os.makedirs('./.data', exist_ok=True)
    printer_config = read_config()
    p = printer_connect(printer_config)
    main_menu()
