import configparser
from escpos import printer
import time
from datetime import datetime, timezone
import uuid
import sqlite3
import requests
import json


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


def read_config():
    try:
        # Create a ConfigParser object
        config = configparser.ConfigParser()

        # Read the configuration file 'config.ini'
        config.read('config.ini')

        # Access values from the 'Printer' section of the configuration file
        id_vendor = config.get('Printer', 'idVendor')
        id_product = config.get('Printer', 'idProduct')
        in_ep = config.get('Printer', 'in_ep')
        out_ep = config.get('Printer', 'out_ep')
        profile = config.get('Printer', 'profile')
        chr_width = config.get('Printer', 'chr_width')

        # Return a dictionary with the retrieved configuration values
        config_values = {
            'idVendor': id_vendor,
            'idProduct': id_product,
            'in_ep': in_ep,
            'out_ep': out_ep,
            'profile': profile,
            'chr_width': chr_width
        }

        return config_values

    except configparser.NoSectionError:
        # If the 'Printer' section is not found in the configuration file
        # Create a new configuration with default settings
        config = configparser.ConfigParser()

        # Add default sections and key-value pairs for the printer
        config['Printer'] = {
            'idVendor': '0x0416',
            'idProduct': '0x5011',
            'in_ep': '0x81',
            'out_ep': '0x03',
            'profile': 'TM-P80',
            'chr_width': '48'
        }

        # Write the default configuration to 'config.ini'
        with open('config.ini', 'w') as configfile:
            config.write(configfile)

        # Prompt the user to configure the printer and exit the program
        print("Please use the config.ini file to configure your printer.")
        exit(1)


def printer_connect(config):
    # takes config data and sets up definition for the escpos repo
    # Initialize USB printer with the configuration settings
    esc_pos = printer.Usb(
        int(config['idVendor'], 16),
        int(config['idProduct'], 16),
        in_ep=int(config['in_ep'], 16),
        out_ep=int(config['out_ep'], 16),
        profile=str(config['profile'])
    )
    return esc_pos


def check_history_db():
    db = sqlite3.connect(f'./.data/history.db')  # Defines DB
    cur = db.cursor()  # Defines cursor

    # Make sure default_lists db_table exists
    cur.execute('''CREATE TABLE IF NOT EXISTS lists (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        UUID TEXT UNIQUE NOT NULL,
        creation_time INTEGER UNIQUE NOT NULL
    )''')
    db.commit()

    # Make sure default_lists_items db_table exists
    cur.execute('''CREATE TABLE IF NOT EXISTS lists_items (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        default_lists_id INTEGER,
        name TEXT NOT NULL,
        qty INTEGER NOT NULL,
        FOREIGN KEY (default_lists_id) REFERENCES default_lists(UUID)
    )''')
    db.commit()

    # Closes up shop
    cur.close()
    db.close()


def check_current_db():
    db = sqlite3.connect(f'./.data/current.db')  # Defines DB
    cur = db.cursor()  # Defines cursor

    # Make sure inventory db_table exists
    cur.execute('''CREATE TABLE IF NOT EXISTS inventory (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        upc  INTEGER UNIQUE NOT NULL,
        qty INTEGER NOT NULL,
        description TEXT,
        time_first_added INTEGER,
        category TEXT
    )''')
    db.commit()

    # Make sure default_lists db_table exists
    cur.execute('''CREATE TABLE IF NOT EXISTS default_lists (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        UUID TEXT UNIQUE NOT NULL,
        name TEXT UNIQUE NOT NULL
    )''')
    db.commit()

    # Make sure default_lists_items db_table exists
    cur.execute('''CREATE TABLE IF NOT EXISTS default_lists_items (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        default_lists_id INTEGER,
        name TEXT NOT NULL,
        upc  INTEGER UNIQUE NOT NULL,
        qty INTEGER NOT NULL,
        description TEXT,
        time_first_added INTEGER,
        category TEXT,
        FOREIGN KEY (default_lists_id) REFERENCES default_lists(ID)
    )''')
    db.commit()

    # Closes up shop
    cur.close()
    db.close()


def search_db(database: str, db_table: str, term, value):
    db = sqlite3.connect(f'./.data/{database}.db')  # Defines DB to db
    cur = db.cursor()  # Defines cursor

    if term and value:
        # Cursor searches for data
        query = f'SELECT * FROM {db_table} WHERE {term} = ?'
        cur.execute(query, (value,))

        # Returns item
        result = []
        for row in cur:
            result.append(row)

        # Closes up shop
        cur.close()
        db.close()

    else:
        # Gets all items
        query = f'SELECT * FROM {db_table}'
        cur.execute(query,)

        # Returns item
        result = []
        for row in cur:
            result.append(row)

    return result


def add_remove_db(database: str, db_table: str, add=True, **kwargs):
    db = sqlite3.connect(f'./.data/{database}.db')  # Defines DB to db
    cur = db.cursor()  # Defines cursor

    if add:
        # Check to see if the item exists
        try:
            # Construct the column names and placeholders for values
            columns = ', '.join(kwargs.keys())
            placeholders = ', '.join(['?'] * len(kwargs))

            # Construct the SQL query
            query = f'INSERT INTO {db_table} ({columns}) VALUES ({placeholders})'

            # Execute the query
            cur.execute(query, tuple(kwargs.values()))
            db.commit()

        except sqlite3.IntegrityError: # If it exists
            print('Already in database.')
            return

    else:
        if kwargs['id']: # Only allow deletion if database ID is known

            # Construct the SQL DELETE statement
            query = f'DELETE FROM {db_table} WHERE ID = ?'

            # Execute the query
            db_id = str(kwargs['id'])
            cur.execute(query, db_id)
            db.commit()

        else:
            print('Can only delete if database ID is known.')

    # Closes up shop
    cur.close()
    db.close()


def mod_qty_db(database: str, db_table: str, db_id: int, mod=1, add=True):
    db = sqlite3.connect(f'./.data/{database}.db')  # Defines DB to db
    cur = db.cursor()  # Defines cursor

    if add: # To do an addition
        # Construct the SQL UPDATE statement
        query = f'UPDATE {db_table} SET qty = qty + ? WHERE ID = ?'


        # Execute the query
        cur.execute(query, (mod, db_id))

        # Commit the changes
        db.commit()

        # Close the connection
        cur.close()
        db.close()

    else: # For subtraction
        # Construct the SQL UPDATE statement
        query = f'UPDATE {db_table} SET qty = qty - ? WHERE ID = ?'

        # Execute the query
        cur.execute(query, (mod, db_id))

        # Commit the changes
        db.commit()

        # Close the connection
        cur.close()
        db.close()


def fetch_info(upc):
    # Fetch information from the UPC Item DB API
    url = f'https://api.upcitemdb.com/prod/trial/lookup?upc={upc}'
    response = requests.get(url)

    try:
        response.raise_for_status()
        upc_data = json.loads(response.text)
        rate_limit_remaining = response.headers['X-RateLimit-Remaining']
        rate_limit_reset = response.headers['X-RateLimit-Reset']

        if upc_data['items']: # If the item was found
            return upc_data['items'], rate_limit_remaining, rate_limit_reset

        else: # If the item was not found
            return False, rate_limit_remaining, rate_limit_reset

    except requests.exceptions.HTTPError:
        rate_limit_remaining = response.headers['X-RateLimit-Remaining']
        rate_limit_reset = response.headers['X-RateLimit-Reset']
        return False, rate_limit_remaining, rate_limit_reset


def get_item_info_by_upc():
    """
    Prompts the user for a UPC, checks inventory and fetches from an external API if needed.
    Returns a tuple (item_name, description, category, upc) or None if the user decides to go back.
    """
    while True:
        upc = input("Enter item UPC (0 to go back): ")
        if upc == '0':
            return None  # Signal to go back

        # Check if the item exists in the inventory
        inventory_item = search_db('current', 'inventory', 'upc', upc)
        if inventory_item:
            # Use the information from the inventory
            item_name = inventory_item[0][1]
            description = inventory_item[0][4]
            category = inventory_item[0][6]
            print(f"Item '{item_name}' found in inventory.")
            return item_name, description, category, upc

        # Fetch information from the external API if item not found in inventory
        fetch = fetch_info(upc)
        remaining = fetch[1]
        until = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(int(fetch[2])))

        # Display the remaining API searches
        print(f"You have {remaining} search(es) remaining until {until}.")

        if fetch[0] and isinstance(fetch[0], list) and len(fetch[0]) > 0:  # If product was found in the API
            product_info = fetch[0][0]  # Assuming fetch[0] is a list of dictionaries

            # Ensure product_info is a dictionary
            if isinstance(product_info, dict):
                item_name = product_info.get('title', 'Unknown')
                description = product_info.get('description', 'No description available')
                category = product_info.get('category', 'Uncategorized')
                print(f"Item '{item_name}' found via API.")
                return item_name, description, category, upc

        # Prompt the user for a name if the item was not found in the API
        while True:
            item_name = input(BColors.WARNING + 'Enter product name (0 to go back): ' + BColors.END_C)
            if item_name == '0':
                break  # Go back to UPC entry
            if item_name:
                break
        if item_name == '0':
            continue  # Go back to the UPC input

        description = input("Enter description: ")
        category = input("Enter category: ")

        return item_name, description, category, upc


def user_items_to_inventory():
    check_current_db()

    # Allow user to add items
    menu = True
    while menu is True:
        print('Add item: ')

        # Gets current time
        cur_time = int(time.time())

        # Gives user an out
        upc = input('Enter UPC (0 for exit): ')
        if int(upc) == 0:
            return

        # Determines if item is in inventory by UPC
        search = search_db('current', 'inventory', 'upc', upc)
        if search:
            mod_qty_db('current', 'inventory', search[0][0], 1)
            print(search[0][1])  # noqa

        else:
            # Search for item UPC and parse
            fetch = fetch_info(upc)
            remaining = fetch[1]
            until = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(int(fetch[2])))

            # Let user know data rates
            print(f'You have {remaining} search(s) until {until}')

            if fetch[0]: # noqa
                # If product lookup was true, use that
                product_info = fetch[0][0]
                new_item = {'name': product_info['title'], 'upc': upc, # noqa
                            'qty': 1, 'description': product_info['description'], 'time_first_added': cur_time} # noqa
                print(product_info['title']) # noqa

            else: # If no info was found, prompt user
                # Structure user input
                while True:
                    possible_name = input(BColors.WARNING + 'Enter product name (0 for exit): ' + BColors.END_C)
                    try:
                        if int(possible_name) == 0:
                            return
                    except ValueError:
                        name = possible_name
                        break

                new_item = {'name': name, 'upc': upc,
                            'qty': 1, 'description': input('Enter description:'), 'time_first_added': cur_time}

            add_remove_db('current', 'inventory',
                          add=True, name= new_item['name'], upc=new_item['upc'], qty=new_item['qty'],
                          description=new_item['description'], time_first_added=new_item['time_first_added'])


def user_items_from_inventory():
    check_current_db()

    # Allow user to add items
    menu = True
    while menu is True:
        print('Remove item: ')

        # Gives user an out
        upc = input('Enter UPC (0 for exit): ')
        if int(upc) == 0:
            return

        # Determines if item is in inventory by UPC
        search = search_db('current', 'inventory', 'upc', upc)

        if search: # Checks and makes sure item is in inventory
            if not int(search[0][3]) <= 0:
                mod_qty_db('current', 'inventory', search[0][0], add=False)  # Removes 1 qty
                print(search[0][1])

            else:
                print(BColors.WARNING +  f'{search[0][1]} has 0 in inventory already.' + BColors.END_C)


        else: # If not in inventory let user know
            print(BColors.WARNING + 'Item is not currently in inventory.' + BColors.END_C)


def add_default_shopping_list(list_name):
    check_current_db()

    # Check if the default shopping list already exists
    existing_list = search_db('current', 'default_lists', 'name', list_name)

    if existing_list:
        print(f"The shopping list '{list_name}' already exists.")
        return

    # Add new shopping list
    new_list = {
        'UUID': str(uuid.uuid4()),
        'name': list_name
    }

    add_remove_db('current', 'default_lists', add=True, **new_list)
    print(f"Shopping list '{list_name}' has been added.")


def edit_default_shopping_list():
    # Retrieve and display current default shopping lists
    shopping_lists = search_db('current', 'default_lists', None, None)

    if not shopping_lists:
        print("No default shopping lists found.")
        return

    print("Default Shopping Lists:")
    for idx, shopping_list in enumerate(shopping_lists, start=1):
        print(f"{idx}. {shopping_list[2]}")  # Display list name

    # Prompt user to select a list to edit
    try:
        selection = int(input("Select a shopping list to edit (0 to exit): "))
    except ValueError:
        print("Invalid input.")
        return

    if selection == 0:
        return

    selected_list = shopping_lists[selection - 1]
    list_id = selected_list[0]

    while True:
        # Loop for selecting add or remove mode
        action = input("Enter 'add' to add items, 'remove' to remove items, 'exit' to finish: ").lower()

        if action == 'exit':
            break
        elif action not in ('add', 'remove'):
            print("Invalid action.")
            continue

        # Sub-loop for continuously adding or removing items
        while True:
            if action == 'add':
                # Use get_item_info_by_upc() to get item information
                item_info = get_item_info_by_upc()
                if not item_info:
                    break  # Go back to the add/remove prompt

                item_name, description, category, upc = item_info

                # Get the quantity and the current time
                qty = int(input("Enter quantity: "))
                time_added = int(time.time())

                # Add the item to the default shopping list
                new_item = {
                    'default_lists_id': list_id,
                    'name': item_name,
                    'upc': upc,
                    'qty': qty,
                    'description': description,
                    'time_first_added': time_added,
                    'category': category
                }

                add_remove_db('current', 'default_lists_items', add=True, **new_item)
                print(f"Item '{item_name}' added to shopping list.")

            elif action == 'remove':
                upc = input("Enter the UPC of the item to remove (0 to go back): ")
                if upc == '0':
                    break  # Go back to the add/remove prompt

                # Check if item exists in the default shopping list
                items = search_db('current', 'default_lists_items', 'upc', upc)
                if not items:
                    print("Item not found in the list.")
                    continue

                # Remove the item by its ID
                item_id = items[0][0]
                add_remove_db('current', 'default_lists_items', add=False, id=item_id)
                print("Item removed from the list.")


def delete_default_shopping_list(list_name):
    check_current_db()

    # Check if the shopping list exists
    shopping_list = search_db('current', 'default_lists', 'name', list_name)

    if not shopping_list:
        print(f"The shopping list '{list_name}' does not exist.")
        return

    # Remove the shopping list
    list_id = shopping_list[0][0]
    add_remove_db('current', 'default_lists', add=False, id=list_id)
    print(f"Shopping list '{list_name}' has been deleted.")

    # Clean up related items in default_lists_items
    db = sqlite3.connect(f'./.data/current.db')
    cur = db.cursor()
    cur.execute('DELETE FROM default_lists_items WHERE default_lists_id = ?', (list_id,))
    db.commit()
    cur.close()
    db.close()
    print(f"Items associated with '{list_name}' have been deleted.")


def print_pdf417(content, width=2, rows=0, height_multiplier=0, data_column_count=0, ec=20, options=0):
    # Generate a PDF417 barcode command sequence for the printer
    # TODO Add error calling when generation fails
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

    # Validate content length
    if len(content) + 3 >= 500:
        return 'TOO LARGE'
    content = content.encode('utf-8')  # Encode content as UTF-8

    # Validate width
    width = int(width)
    if not 2 <= width <= 8:
        return 'width must be between 2 and 8'

    # Validate rows
    rows = int(rows)
    if not 3 <= rows <= 90:
        if not rows == 0:  # rows can be 0 for auto
            return "rows must be 0 for auto, or between 3 and 90"

    # Validate height_multiplier
    height_multiplier = int(height_multiplier)
    if not 0 <= height_multiplier <= 16:
        return 'height_multiplier must be between 0 and 16'

    # Validate data_column_count
    data_column_count = int(data_column_count)
    if not 0 <= data_column_count <= 30:
        return 'data_column_count must be between 0 and 30'

    # Validate error correction (ec)
    ec = int(ec)
    if not 1 <= ec <= 40:
        return 'ec must be between 1 and 40'

    # Validate options
    options = int(options)
    if options not in [0, 1]:  # 0 for standard, 1 for truncated
        return 'options must be set 0 for standard or 1 for truncated'

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
    p._raw(data) # noqa


def print_header():
    # Print the header including the logo and current date/time
    p.hw('INIT')  # Initializes the printer
    p.image('./assets/logo.png', center=True)  # Print the logo
    p.hw('INIT') # Initializes the printer after printing image
    p.ln(2)  # Add line breaks
    now = datetime.now(timezone.utc).strftime('%m/%d/%Y %H:%M:%S %Z')  # Current time in UTC
    p.text('Printed at: %s' % now)  # Print the timestamp


def print_line():
    # Print a horizontal line across the width of the printer
    line = '-' * int(printer_config['chr_width'])  # Create the line with '-' repeated
    p.text(line)  # Print the line


def r_l_justify(str_a, str_b, space_chr=' '):
    # Prints two strings where one is justified to the left and one to the right
    # Validating the space_chr
    if space_chr == "":
        p.text('SPACE_CHR CANNOT BE EMPTY')
        return 'SPACE_CHR CANNOT BE EMPTY'
    if len(space_chr) != 1:
        p.text('SPACE_CHR CANNOT BE LONGER THAN 1')
        return 'SPACE_CHR CANNOT BE LONGER THAN 1'
    both_length = len(str_a) + len(str_b) # Gets the total len of both str
    if both_length > int(printer_config['chr_width']): # Makes sure that both str fit
        amt_to_trim = int(printer_config['chr_width']) - (len(str_b) + 5)
        str_a = str_a[:amt_to_trim]
        str_a += '...'
        both_length = len(str_a) + len(str_b)
    added_chr = int(printer_config['chr_width']) - both_length
    spaces = space_chr * added_chr # Generates the needed spaces
    final = str_a + spaces + str_b # Combines everything
    p.hw('INIT') # Initializes the printer, because it won't work reliably with effects
    p.text(final) # Prints the justified line


def print_list(items, list_uuid = None, barcode = True):
    # Prints a shopping list with the given data
    if not list_uuid: # Checks to see if a UUID was supplied and if not generates one
        list_uuid = uuid.uuid4()  # Generates a UUID for the list
    creation_time = int(time.time())
    # Print items justified r to l
    for x in items:
        r_l_justify(str(x[0]),str(x[1])) # Prints name and qty r-l justified
    p.ln(1)  # new line after items
    if barcode:
        print_pdf417(str(list_uuid), width=3) # Prints list UUID as pdf417 barcode
    # Prepare output data
    output = {'time_generated': creation_time, 'uuid': list_uuid}
    return output, items


def inventory_report():
    # Get all inventory
    data = search_db('current', 'inventory', None, None)
    items = [(item[1], item[3]) for item in data]

    # Print report
    print_header()
    p.ln(2) # New line
    p.set(double_height=True, double_width=True, align='center') # Set large test
    p.text('Inventory Report') # Print text
    p.ln(1)  # New line
    p.hw('INIT') # Initializes printer
    print_list(items, barcode=False)
    p.cut() # Cut page


def compare_default_list_to_inventory(default_list_id):
    # Ensure the database tables exist
    check_current_db()

    # Fetch items from the default shopping list by ID
    default_list_items = search_db('current', 'default_lists_items', 'default_lists_id', default_list_id)

    if not default_list_items:
        print(f"No items found on list searched.")
        return []

    # Create a dictionary of inventory items with name as keys for quick lookup
    inventory_items = search_db('current', 'inventory', None, None)
    inventory_dict = {item[1]: item for item in inventory_items}  # item[1] is the name

    # List to store the tuples of items and their required quantities to add
    items_to_add = []

    # Compare each item in the default shopping list with the current inventory
    for item in default_list_items:
        default_name = item[2]  # Name in default list item
        default_qty = item[4]  # Required quantity in default list

        # Check if the item is in the inventory
        if default_name in inventory_dict:
            inventory_qty = inventory_dict[default_name][3]  # Quantity in inventory (item[3] is qty in inventory)

            # Calculate the difference if inventory is less than required quantity
            if inventory_qty < default_qty:
                qty_needed = default_qty - inventory_qty
                items_to_add.append((item[2], qty_needed))  # Append (item name, qty needed)
        else:
            # Item is not in inventory, need to add full default list quantity
            items_to_add.append((item[2], default_qty))  # Append (item name, qty needed)

    return items_to_add


def create_shopping_list():
    # Ensure the database tables exist
    check_current_db()

    # Fetch and display current default shopping lists
    shopping_lists = search_db('current', 'default_lists', None, None)

    if not shopping_lists:
        print("No default shopping lists available.")
        return

    print("Default Shopping Lists:")
    for idx, shopping_list in enumerate(shopping_lists, start=1):
        print(f"{idx}. {shopping_list[2]}")  # Display list name

    # Prompt user to select a default shopping list
    try:
        selection = int(input("Select a default shopping list to create (0 to exit): "))
    except ValueError:
        print("Invalid input.")
        return []

    if selection == 0:
        return []

    selected_list_id = shopping_lists[selection - 1][0]

    # Generate items needed based on the default shopping list and current inventory
    items_needed = compare_default_list_to_inventory(selected_list_id)
    print(f"Initial items needed to match default shopping list: {items_needed}")

    # List to store manually added items
    additional_items = []

    # Sub-loop for adding additional items
    while True:
        action = input("Would you like to manually add more items? (yes/no): ").lower()

        if action == 'no':
            break
        elif action != 'yes':
            print("Invalid action. Please enter 'yes' or 'no'.")
            continue

        # Adding additional items using get_item_info_by_upc
        while True:
            item_info = get_item_info_by_upc()
            if not item_info:
                break  # Go back to the yes/no prompt

            item_name, description, category, upc = item_info

            # Get the quantity and add the item to the additional_items list
            qty = int(input("Enter quantity: "))
            additional_items.append((item_name, qty))

    # Compare additional items to the current inventory
    additional_items_to_add = []
    for item_name, qty in additional_items:
        # Check if the item is in the inventory
        inventory_item = search_db('current', 'inventory', 'name', item_name)
        if inventory_item:
            inventory_qty = inventory_item[0][3]  # Quantity in inventory
            # Calculate the difference if inventory is less than the needed quantity
            if inventory_qty < qty:
                qty_needed = qty - inventory_qty
                additional_items_to_add.append((item_name, qty_needed))
        else:
            # Item is not in inventory, need to add full quantity
            additional_items_to_add.append((item_name, qty))

    # Combine the items needed from the default list and the additional items
    combined_items_needed = items_needed + additional_items_to_add

    print(f"Final list of items and quantities needed: {combined_items_needed}")
    return combined_items_needed


def print_shopping_list(items):
    # Ensure history DB is online
    check_history_db()

    # Verify items
    if not items:
        return

    # Print list
    print_header()
    p.ln(2)  # New line
    p.set(double_height=True, double_width=True, align='center')  # Set large text
    p.text('Shopping list')  # Print text
    p.ln(2)  # New line
    p.hw('INIT')  # Initializes printer

    # Generate the list and get the output dictionary and items
    output, items = print_list(items)

    # Extract creation_time and list_uuid from the output dictionary
    creation_time = output['time_generated']
    list_uuid = str(output['uuid'])

    p.cut() # Cuts paper

    # Add the list UUID and creation time to the 'history' database in the 'lists' table
    try:
        add_remove_db(
            database='history',
            db_table='lists',
            add=True,
            UUID=list_uuid,
            creation_time=creation_time
        )
    except Exception as e:
        print(f"Error adding list to history database: {e}")

    # Add each item to the 'history' database in the 'default_lists_items' table
    for item in items:
        try:
            # Ensure that item is a tuple with two elements
            item_name, qty = item
            add_remove_db(
                database='history',
                db_table='lists_items',
                add=True,
                default_lists_id=list_uuid,  # Use the UUID as the foreign key reference
                name=item_name,
                qty=qty
            )
            print(f"Item '{item_name}' with quantity {qty} added to 'history' database under list UUID {list_uuid}.")
        except Exception as e:
            print(f"Error adding item '{item}' to history database: {e}")


def reports_menu():
    while True:
        print(BColors.HEADER + 'Reports' + BColors.END_C)
        print('1. Inventory Report')
        print('2. Default Lists Report')
        print('0. Return to Main Menu')

        choice = input('Enter your choice: ')

        if choice == '0':
            break  # Exit the reports menu

        elif choice == '1':
            # Generate and print the inventory report
            inventory_report()

        elif choice == '2':
            # Generate and print the default lists report
            #default_lists_report()
            pass

        else:
            print('Invalid choice. Please select a valid option.')


def default_shopping_list_menu():
    while True:
        print(BColors.HEADER + 'Default Shopping List Management' + BColors.END_C)
        print('1. Add a new default shopping list')
        print('2. Edit an existing default shopping list')
        print('3. Delete a default shopping list')
        print('0. Return to main menu')

        choice = input('Enter your choice: ')

        if choice == '0':
            break  # Exit the submenu

        elif choice == '1':
            # Add a new default shopping list
            list_name = input('Enter the name of the new shopping list: ')
            add_default_shopping_list(list_name)

        elif choice == '2':
            # Edit an existing default shopping list
            edit_default_shopping_list()

        elif choice == '3':
            # Delete a default shopping list
            list_name = input('Enter the name of the shopping list to delete: ')
            delete_default_shopping_list(list_name)

        else:
            print('Invalid choice. Please select a valid option.')


def chr_test():
    # Test the character width of the printer
    p.hw('INIT')  # Initialize hardware
    p.set(align='center', custom_size=True, height=4, width=4, invert=True)  # Set text properties for header
    p.text('CHR TEST\n')  # Print 'CHR TEST'
    p.hw('INIT')  # Initialize hardware
    p.text('--------------------------------------------------------------------------------------------------\n')
    p.text('Current setting is: %s\nThat looks like this...\n' % printer_config['chr_width'])  # Print current setting
    print_line()  # Print a line


def pdf417_test():
    # Test the character width of the printer
    p.hw('INIT')  # Initialize hardware
    p.set(align='center', custom_size=True, height=4, width=4, invert=True)  # Set text properties for header
    p.text('PDF417 TEST\n')  # Print 'PDF417 TEST'
    p.hw('INIT')  # Initialize hardware
    content = '''
    !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~
    ''' # noqa Content of the barcode
    sequence = print_pdf417(content) # Generates PDF471 sequence
    p._raw(sequence) # noqa Sends the sequence to the printer


def list_test():
    p.hw('INIT')  # Initializes the printer
    p.set(align='center', custom_size=True, height=4, width=4, invert=True)  # Set text properties for header
    p.text('LIST TEST\n')
    p.hw('INIT')  # Initializes printer after header
    items = [('Apple', 1), ('Milk', 14), ('Banana', 69), ('Soda', 4)]
    data_out = print_list(items)
    p.hw('INIT')  # Initialize hardware
    p.ln(1)
    p.text('DEBUG:\n')
    p.text(data_out)


def print_debug(*args):
    # Master list of tests to run
    tests_list = {
        'header': print_header,
        'chr': chr_test,
        'pdf417': pdf417_test,
        'list': list_test
    }

    # Allow fetching the tests_list from outside the function
    if 'get_list' in args:
        return tests_list

    # Determine which functions to run
    if not args:
        # If args is empty, run all functions
        tests_to_run = tests_list.items()
    else:
        # If args is not empty, filter functions based on args
        tests_to_run = [(test_name, func) for test_name, func in tests_list.items() if test_name in args]

    tests_ran = '' # Initialize logging of tests ran

    for test_name, func in tests_to_run:
        func()  # Execute the function
        p.ln(2) # New line after test
        tests_ran += str(func)
    p.cut()  # Cut the page
    return tests_ran


def main_menu():
    while True:
        print(BColors.HEADER + 'GroceryListDB' + BColors.END_C)
        print('1. Add items to inventory')
        print('2. Remove items from inventory')
        print('3. Create shopping list')
        print('4. Set up default shopping lists')
        print('5. Historical shopping lists')
        print('6. Reports')
        print('7. Print test page')
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
            # Call the default shopping list submenu
            default_shopping_list_menu()

        elif choice == '6':
            # Call the reports menu
            reports_menu()

        elif choice == '7':
            print_debug()

        else:
            print('Invalid choice. Please select a valid option.')

# Set up escpos
printer_config = read_config()
p = printer_connect(printer_config)

main_menu()