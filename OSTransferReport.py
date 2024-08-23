from pandas import read_excel, read_csv, DataFrame
import re
import webbrowser
import os
import tomllib 


def main():
    # Open file and load it into dataframe info
    print("Loading file")
    df = read_csv("FinalePythonReport.csv", dtype='object')

    print("Reading config")
    config = read_config("config.toml")

    # Create title and description of report
    title = config["header"]["title"] 
    description = config["header"]["description"]

    # create sections of report
    sections = []
    for section in config["sections"]:
        sections.append(Section(df, config["sections"][section], 
                                config["options"]["exclusions"]))

    # Create sections of report. if section is empty after calculation,
    # it will not be shown on the report.

    # Write output to file
    print("Writing Output")
    html_output = ""
    for section in sections:
        html_output += section.html 

    write_output(title, description, html_output)

    browser_open('OSTransferReport.html')


def read_config(filename):
    with open(filename, "rb") as file:
        config = tomllib.load(file)
        return config


def browser_open(filename):
    cwd = os.getcwd()
    webbrowser.open_new_tab('file://' + cwd + '/' + filename)


def write_output(title, description, sections):
    html = f'''
    <html>
      <head>
        <title>{title}</title>
      </head>
      <body>
        <h1 style="margin: auto; display: block; width: 65%; text-align: center;">{title}</h1>
        <p style="margin: auto; display: block; width: 65%; text-align: center; padding-bottom: 15px;">{description}</p>
        {sections}

        <style>
            th, td \u007b 
                padding: 8px;
                cellspacing: 0;
                border-bottom: 1px solid black;
                font-size: 9pt;
                width: 25%;
                max-width: 25%;
            \u007d

            table, th, td \u007b
                border-collapse: collapse;
            \u007d

            table \u007b
                margin-bottom: 30px;
                width: 100%;
            \u007d

            h2 \u007b
                margin-bottom: 10px;
            \u007d
        </style>
    </body>
    </html>
    '''

    # write html file
    with open('OSTransferReport.html', 'w') as f:
        f.write(html)


class Section:
    def __init__(self, df, section_data, exclusions):
        print(f'creating {section_data["title"]} section')
        self.section_data = section_data
        self.subset_filter = "|".join(section_data['subsets'])
        self.filtered_df = self.filter_data(df)

        self.items = self.create_items(self.filtered_df, exclusions)
        self.dictionary = self.create_dict(self.items)
        self.html = self.create_html(self.dictionary, section_data["title"])
        
    def filter_data(self, df):
        print("Filtering data")
        df.dropna(how="all", axis=0, inplace=True) # Drop any NaN rows

        df.fillna("0", inplace=True) # Replace any NaN values with 0

        df = df[df["Supplier Subset"].str.contains(self.subset_filter)] # Filter dataframe based on Supplier Subset
        df = df[df["Location QoH"].astype(int) > 0] # Filter out anything with 0 QoH
        
        # filter unused columns and combine columns with the same product id
        df["Location QoH"] = df["Location QoH"].astype("string")
        df = df.groupby(['Product ID', 'Std packing', 'Supplier'], as_index=False).agg({'Location QoH': ', '.join, 'Sublocation': ', '.join})
        df = df.rename(columns={"Sublocation": "All Sublocations"})
        df = df[['Product ID', 'All Sublocations', 'Std packing', 'Supplier', 'Location QoH']]

        return df
    
    def create_items(self, df, exclusions):
        items = []

        for line in df.to_numpy():
            id = line[0]
            subloc = line[1]
            std_packing = line[2]
            supplier = line[3]
            qoh = line[4]
            items.append(Item(id, subloc, qoh, std_packing, supplier, self.section_data, exclusions))

        return items
    
    def create_dict(self, all_items):
        new_dict = {
            'Product ID': [],
            'Picking Sublocations': [],
            'Overstock Sublocations': [],
            'Standard Packing': []
             }
        
        for item in all_items:
            if item.is_transfer:
                new_dict['Product ID'].append(item.product_id)
                new_dict['Picking Sublocations'].append(", ".join(item.p_summary))
                new_dict['Overstock Sublocations'].append(", ".join(item.os_summary))
                new_dict['Standard Packing'].append(item.std_packing)

        return new_dict
    
    def create_html(self, dict, header):
        if dict['Product ID'] == []:
            html = ""
        else:
            df = DataFrame(data=dict)
            html = f'<h2>{header}</h2>\n{df.to_html(index=False, border=0, justify="left")}'
        
        return html
    

class Item:
    def __init__(self, id, sublocs, qtys, stdpack, supplier, section_data, exclusions):
        self.product_id = id
        self.all_sublocations = sublocs
        self.all_quantities = qtys
        self.std_packing = stdpack
        self.supplier = supplier
        self.exclusions = exclusions
        self.section_data = section_data

        self.all_sublocations = self.all_sublocations.split(", ")
        self.all_quantities = self.all_quantities.split(", ")

        self.os_loc, self.os_qty = self.sort_sublocations(self.all_sublocations, self.all_quantities, 'overstock')
        self.pick_loc, self.pick_qty = self.sort_sublocations(self.all_sublocations, self.all_quantities, 'picking')

        self.is_transfer = self.calc_transfer(self.product_id, self.os_loc, self.pick_qty, self.supplier, filter)

        self.os_summary = self.create_sublocation_summary(self.os_loc, self.os_qty)
        self.p_summary = self.create_sublocation_summary(self.pick_loc, self.pick_qty)
    
    def sort_sublocations(self, sublocs, qty, location_type):
        locs = []
        loc_qtys = []
        if location_type == "overstock":
            search_str = "^[A1RT].[-VM].+" # search for "A", "11", "12", "TEMP" or "RCVPREP" locations
        elif location_type == "picking":
            search_str = "^0.-0.+"

        for x in range(0, len(qty)):
            if re.search(search_str, sublocs[x]):
                locs.append(sublocs[x])
                loc_qtys.append(qty[x])
        
        return locs, loc_qtys
    
    def calc_transfer(self, id, os_loc, p_qty, supplier, filter):
        # if item is in exclusions list, return false value
        for item in self.exclusions:
            if re.search(id, item):
                return False
            
        # if item has more than one picking location, return false value
        if len(p_qty) > 1:
            return False

        # check that supplier is on the list, and calculate if item should be transferred based on quantity
        for s in self.section_data['supplier_minimums']:
            if re.search(s, supplier):
                if os_loc == []:
                    transfer = False
                elif p_qty == [] and os_loc != []:
                    transfer = True
                    break
                else:
                    for x in range(0, len([p_qty])):
                        if int(p_qty[x]) <= self.section_data["supplier_minimums"].get(s):
                            transfer = True
                            break
                        else:
                            transfer = False
            else:
                transfer = False

            if transfer: break

        return transfer
    
    def create_sublocation_summary(self, all_locations, all_qtys):
        summary = []
        for x in range(len(all_locations)):
            summary.append(f'{all_locations[x]}: {all_qtys[x]}')

        return summary
    

if __name__ == '__main__':
    main()
