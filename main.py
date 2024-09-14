import configparser
from escpos import printer
from datetime import datetime, timezone


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


def pdf417(content, width=2, rows=0, height_multiplier=0, data_column_count=0, ec=20, options=0):
    # Generate a PDF417 barcode command sequence for the printer

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
    p.image('./assets/logo.png', center=True)  # Print the logo
    p.ln(3)  # Add line breaks
    now = datetime.now(timezone.utc).strftime('%m/%d/%Y %H:%M:%S %Z')  # Current time in UTC
    p.text('Printed at: %s\n' % now)  # Print the timestamp


def print_line():
    # Print a horizontal line across the width of the printer
    line = '-' * int(printer_config['chr_width'])  # Create the line with '-' repeated
    p.text(line)  # Print the line


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
    content = '''
    !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~
    ''' # noqa Content of the barcode
    sequence = pdf417(content) # Generates PDF471 sequence
    p._raw(sequence) # noqa Sends the sequence to the printer

# Load printer configuration
printer_config = read_config()

# Initialize USB printer with the configuration settings
p = printer.Usb(
    int(printer_config['idVendor'], 16),
    int(printer_config['idProduct'], 16),
    in_ep=int(printer_config['in_ep'], 16),
    out_ep=int(printer_config['out_ep'], 16),
    profile=str(printer_config['profile'])
)

p.hw("INIT")
print_header()
p.ln(1)
chr_test()
p.ln(2)
p.hw('INIT')
pdf417_test()
p.cut()
