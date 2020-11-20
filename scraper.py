import re
import os
import sys
import time
import shutil
import config # for global variable storage
import traceback
import pandas as pd
from word2number import w2n
from tqdm.notebook import tqdm
from concurrent.futures import TimeoutError                                  

# for browser interaction & load waiting:
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


config.download_dir = '../../Downloads' # *** <——— set the default browser download folder ***


# to ignore .DS_store files etc. 
def listdir_nohidden(path):
    def generator():
        for f in os.listdir(path):
            if not f.startswith('.'):
                yield f
    return list(generator())



# find a target element on the page
def wait_for(element, by, timeout=10, multi=False):
    global d
    for i in range(int(timeout/2)):
        time.sleep(.25)
        try:
            WebDriverWait(d, .5).until(
                EC.presence_of_element_located((by, element)))
            time.sleep(.25)
            if multi: return d.find_elements(by, element)
            else: return d.find_element(by, element)
        except:
            pass            
    raise TimeoutError(f"""
    ERROR: Timed out searching for for an element
    DETAILS: seeking {element} | by {by}""")
    
    
    
    
def launch_new_search():
    global d
    # open search panel
    url = 'https://scerisecm.boston.gov/ScerIS/CmPublic/#/Home'
    open_search = '/html/body/div[1]/div/div/div[2]/div[3]/search-dashboard/div/div/div[2]/div/div/div/div/ul/li[3]/dashboard-folders-renderer/div/div/div/a[3]'
    try: d
    except: d = False
    if d:
        try: d.get(url)
        except:
            d = False
            try: d.quit()
            except: pass
    if not d:
        d = webdriver.Chrome()
        d.set_window_size(1280,800)
        d.set_window_position(0,0)
        d.get(url)

    wait_for(open_search, By.XPATH).click()
    return d




# creates a dict of search options with element info 
def get_search_params(verb=True):
        
    # define search params and their corresponding input elements on the page
    params = wait_for("div[ng-repeat='dynamicTerm in dynamicSearchFieldTerms'",
                      By.CSS_SELECTOR, multi=True)
    
    
    names = [p.text.split('\n')[0] for p in params]
    selectors = [p.find_element(By.CLASS_NAME, 'dropdown')
                 if 'Permit Num' in p.text or 'Permit Date' in p.text else '' for p in params ]
    
    input_containers = wait_for('input-with-help', By.CLASS_NAME, multi=True)
    inputs = [i.find_element_by_tag_name('input') for i in input_containers]
    
    
    show_opts = [
            p.find_element_by_css_selector(
                "input[ng-change='setSearchCriteriaAndDisplayFieldsUserPreference();']")
            for p in params
                ]

    
    # list available params
    search_param = {n: {'title':p,'input':i, 'selector':s, 'show':o}  for n, p, i, s, o in
                                            zip(names, params, inputs, selectors, show_opts)}
    
    # assign to global 
    config.search_param = search_param

    
    
    
# gets list of all wards from the ward search option dropdown
def get_wards():
    d = launch_new_search()
    ward_list = wait_for('UniqueID49', By.ID)
    ward_names = ward_list.find_elements_by_tag_name('option')
    out = list(set([w.get_attribute('value').upper() for w in ward_names]))
    print(len(out), 'unique wards identified')
    d.quit()
    return out



# input keys to target search param
def set_search(param, keys):
    param = config.search_param[param]
    d.execute_script("arguments[0].scrollIntoView();", param['title'])
    time.sleep(.15)
    
    if keys == '':
        param['selector'].find_element(By.CLASS_NAME, 'dropdown-toggle').click()
        time.sleep(.1)
        param['selector'].find_element(By.CSS_SELECTOR, "li[hr-name-map='Blank']").click()
        return
    elif keys == 'since_00': # EXECUTIVE SUITES DID NOT EXIST BEFORE 2000!
        param['selector'].find_element(By.CLASS_NAME, 'dropdown-toggle').click()
        time.sleep(.1) # set greater than or equal to selector
        param['selector'].find_element(By.CSS_SELECTOR, "li[hr-name-map='>=']").click()
        time.sleep(.1)
        param['input'].send_keys('01-01-2000')
        return
    else:
        param['input'].send_keys(keys)
        
        
        
        
# given search params, input and load results
# creates a directory for downloads for this search
# search_param_input => dict of search params and their desired values
# addtl_params => list of non-search params to include in results
def get_results(search_param_input, addtl_params, since_00=True): # SINCE 2000 only by default
    top_param = list(search_param_input.keys())[0]
    top_p_val = search_param_input[top_param]
    
    # ——— initial setup ——— (first search parameter is used to structure file directory)
    print('—'*30)    
    launch_new_search()
    # set download & target save directories
    config.target_dir = f"{top_param.lower().replace(' ', '_')}/{top_p_val}" # files get moved here
    if not os.path.exists(config.target_dir): # create target save directory if needed
        os.makedirs(config.target_dir)
    search_param = get_search_params() # get search params elements
    # disable default "show all" params (default doesn't really show all anyways)
    wait_for("input[data-ng-model='displayAllInResults.displayAll']",
             By.CSS_SELECTOR).click()

    # ——— include addtl params in search results ———
    print('> Filtering results...', end='')
    def set_show_param(param):
        # scroll window to target param
        element = config.search_param[param]['input']
        actions = ActionChains(d)
        actions.move_to_element(element).perform()
        time.sleep(.1)
        # click the target "show" checkbox for this param
        config.search_param[param]['show'].click()
        time.sleep(.1)
    # apply above function to each (input) target from addtl_params
    for a_param in addtl_params:
        set_show_param(a_param)

    # ——— set criteria (values) for main search parameters ———
    print('setting parameters...', end='')
    time.sleep(.5)
    for s_param, s_value in search_param_input.items():
        set_search(s_param, s_value)
        time.sleep(.1)
    if since_00:
        set_search('Permit Date', 'since_00') # hotword
    print('done.')

    # ——— click "Search" button to load results ———
    wait_for('btnSearch', By.ID).click()
    
    
    
    
# sort items (important to maintain static index when failure—>auto restart)
def sort_results_list():
    sorters = wait_for("div[role='columnheader']", By.CSS_SELECTOR)
    action = ActionChains(d)
    action.move_to_element_with_offset(sorters, 130, 5)
    action.pause(.05).click().pause(.05)
    action.move_to_element_with_offset(sorters, 10, 5)
    action.click().pause(.1).click()
    action.perform()
    
    
    
    
# for a given target file index, go through the steps to download it from the results list.
def download_file(item, n, max_down_wait_sec=15):
    
    # compile metadata for this item from HTML table
    item_vals = [v.text for v in item.find_elements(By.CLASS_NAME, 'ui-grid-cell')]
    row_metadata = dict(zip(config.col_names, item_vals))
    row_df = pd.DataFrame([row_metadata])
    
    # drop timestamp from archive date
    p_d = row_metadata['Archive Date'].split(',')[0]
    row_df['Archive Date'] = p_d
    
    # define target download file name
    p_pm = row_metadata['Permit Number']
    p_st = row_metadata['Street Name']
    p_sn = row_metadata['Primary Street Number']
    config.target_fname = f"{p_sn} {p_st} [{p_pm}] {p_d}".replace('/', '_')
    row_df['file_name'] = config.target_fname
    
    # check cache for item:
    pre_files = listdir_nohidden(config.target_dir)
    pre_files = [''.join(p.split('.')[:-1]) for p in pre_files] # w.out extensions
    if any(config.target_fname in f for f in pre_files):
        config.row_done = True
        return # file already downloaded
    
    # clean & build dataframe of metadata for all items in this search
    row_df.drop('Actions', axis=1, inplace=True)
    config.metadata_df = pd.concat([row_df, config.metadata_df])

    
    # go through download click to prompt download for this file (so many clicks.....)
    time.sleep(.1)
    wait_for("button[ng-click='openDocuments()']", By.CSS_SELECTOR).click()
    time.sleep(.1)
    
    # click intial download icon (open file options sidebar)
    print('  > Clicking initial download button…')
    def get_download_icon():
        return wait_for("button[data-pcc-toggle='dialog-download']", By.CSS_SELECTOR)
    click_success = False
    for c_try in range(3): # click then wait
        if click_success: break
        get_download_icon().click()
        for t_wait in range(15): # 1.5 seconds
            indicator = get_download_icon().get_attribute('class')
            time.sleep(.1)
            if 'active' in indicator:
                click_success = True
                break
    if not click_success:
        print('  [ERROR] - Failed to open file details sidebar')
        raise TimeoutError()
        
    # open initial downloads modal
    modal_success = False
    for c_try in range(3): # click then wait
        if modal_success: break
        try:
            wait_for("button[data-pcc-download='download']", By.CSS_SELECTOR).click() 
            for t_wait in range(15): # 1.5 seconds
                try:
                    d.find_element_by_class_name('pcc-overlay-closer')
                    modal_success = True
                    break
                except: time.sleep(.1)
        except: pass
    if not modal_success:
        print('  [ERROR] - Failed to open intial downloads modal')
        raise TimeoutError()

    
    # click the first "save" button
    print('  > Clicking first "Save" button…')
    time.sleep(.1)
    first_save_success = False
    for f_save_try in range(3):  
        try:
            wait_for("pcc-overlay-download", By.CLASS_NAME).click()                    
            save_modal = wait_for("pcc-overlay-fade", By.CLASS_NAME) 
            if 'none' in save_modal.get_attribute('style'): # verify button was pressed
                first_save_success = True
                break
            else: time.sleep(.1) # pause if failed
        except: time.sleep(.1)
    if not first_save_success:
        print('  [ERROR] - could not trigger download dialogue')
        raise TimeoutError()

    # for large files, splice the first first ten pages
    pages = int(d.find_element(By.CSS_SELECTOR, 'span[data-pcc-pagecount]').text)
    if pages > 25:
        try: 
            config.target_fname += '_first10pg'  # indicate splice in file name
            wait_for("rdoRangeCustom", By.ID).click()
            wait_for("txtCustomRange", By.ID).send_keys('1-10')
        except:
            max_down_wait_sec *= 6 # increase max DL timeout if page splice failed
    elif pages > 10:
        max_down_wait_sec *= 4 # increase max DL timeout if 10-25 pages

    # define initial download directory size (to verify new file exists after DL)
    config.o_dl_len = len ( listdir_nohidden(config.download_dir) ) 
        
    # click the second finicky save button (TRIGGER FILE DOWNLOAD)
    d_btn_success = False
    for trigger_c_try in range(3): # trying to click the download button
        if d_btn_success: break # inner loop detected success
        try: # verify button was clicked
            wait_for("OK", By.ID).click() # click button
            for trigger_try in range(5):
                time.sleep(.2)  # keep checking for html change
                # (if success, "modal" is removed the class of <body> )
                body = d.find_element(By.TAG_NAME, 'body')  
                if 'modal' not in body.get_attribute('class'):
                    d_btn_success = True
                    break
        except: time.sleep(.2)
    if not d_btn_success:
        print(f'  [ERROR] - Failed to click the final download button')
        raise TimeoutError()

    # wait for download to trigger (file appears in downloads folder) 
    download_triggered = False
    for check_download in range(5):
        # get new download path directory size
        config.n_dl_len = len ( listdir_nohidden(config.download_dir) ) 
        if config.n_dl_len > config.o_dl_len:
            download_triggered = True
            break
        else:
            time.sleep(.2)
    if not download_triggered:
        print('  [ERROR] - could not trigger download dialogue')
        raise TimeoutError()
        

    # DOWNLOAD TRIGGERED SUCCESSFULLY....
        
    # monitor downloading file for completion
    filename = max([f for f in os.listdir(config.download_dir)],
                    key=lambda x : os.path.getctime(os.path.join(config.download_dir,x)))
    waits = 0
    while '.part' in filename or 'crdownload' in filename: # still downloading
        if waits > max_down_wait_sec*2:
            print("\n  [ERROR] - download timed out (max waits exceeded)!")
            raise TimeoutError()
        # re-define filename to check for 'part' or 'crdownload' (not done)
        filename = max([f for f in os.listdir(config.download_dir)],
                   key=lambda xa : os.path.getctime(os.path.join(config.download_dir,xa)))
        waits += 1
        time.sleep(.5) # half-second iter pause

    # after DL, rename & move to target directory
    config.target_fname += '.' + filename.split('.')[-1] # add back original extension 
    os.rename(os.path.join(config.download_dir, filename),
              os.path.join(config.download_dir, config.target_fname))
    time.sleep(.15)
    shutil.move(os.path.join(config.download_dir, config.target_fname),
                f'{config.target_dir}/{config.target_fname}')
    print(f"    > '{config.target_fname}' downloaded to {config.target_dir}")

    # confirm existence of new file 
    if config.o_len == listdir_nohidden(config.target_dir):
        print(f'  [ERROR] - {config.target_fname} not found after download')
        raise TimeoutError()
    
    # success! 
    config.row_done = True 
    d.find_element(By.ID, "btnBackToSearchResult").click()
    time.sleep(.2)
    
    
    
def scraper_get(search_param_input, addtl_params,
                max_down_wait_sec=5, max_attempts=3,
                start_at=0): # used for re-starting mid-search
    
    # SET PARAMETERS & LOAD SEARCH RESULTS PAGE:
    get_results(search_param_input, addtl_params)
    
    # initialize page data + metadata DF
    first_row = wait_for('ui-grid-row', By.CLASS_NAME)
    row_height = wait_for('ui-grid-row', By.CLASS_NAME).size['height']
    container = d.find_element(By.CSS_SELECTOR, "div[style='overflow: scroll;']")
    inner_container = d.find_element(By.CLASS_NAME, "ui-grid-canvas")
    inner_height = inner_container.size['height']
    rows_shown = round(container.size['height']/row_height)
    total_rows = round(inner_height/row_height)
    config.col_names = [h.text for h in d.find_elements_by_css_selector("div[role='columnheader']")]
    
    print(' > Iterating over', total_rows, 'files...')  
    
    # sort results to maintain static index
    sort_results_list()
          
    # define a function to click on a target row (used in the item iterator)
    def select_row(n):
        container = d.find_element(By.CSS_SELECTOR, "div[style='overflow: scroll;']")
        # for pre-last ten items, auto-click by scrolling to the top
        if n <  total_rows - rows_shown: # top-click row 
            target_y = row_height*n
            d.execute_script(f"arguments[0].scrollTo(0, {target_y})", container)
            time.sleep(.15)
            action = ActionChains(d)
            action.move_to_element_with_offset(container, 5, 5)
            action.click()
            action.perform()
        # for last ten items, manual-click using item index in row list
        else:
            d.execute_script(f"arguments[0].scrollTo(0, {inner_height})", container)
            time.sleep(.1)
            last_back_ten = min(rows_shown, total_rows) - (total_rows-n)
            d.find_elements(By.CLASS_NAME, 'ui-grid-row')[-last_back_ten].click()
            
            
    # START ITERATING OVER ITEMS to download
    # if picking up from auto-restart, begin with the last tried row
    for n in tqdm(range(start_at, total_rows)):
        
        try: 
            # not in cache, trigger file download:    
            print(f'  > Prompting download (file {n+1}/{total_rows})...')                

            config.row_done = False
            pause_step = 4 # wait this much more after each retry

            # for this row, try to download the associated file....
            for attempt in range(max_attempts): # this refers to the main file download function 

                # manage retries on this row:
                if config.row_done: break
                if attempt>0: # log & pause if retrying same file
                    print(f'  >>> Retrying ({attempt}/{max_attempts} attempts)...')
                    time.sleep( pause_step*attempt )
                    try: d.find_element(By.ID, "btnBackToSearchResult").click()
                    except: pass

                # to check later if new file exists:
                config.o_len = len ( listdir_nohidden(config.target_dir) ) 

            # SELECT & DOWNLOAD THIS FILE
                # scroll body container to reveal full table
                footer_tag = d.find_element(By.CLASS_NAME, 'ui-grid-footer-info')
                d.execute_script("arguments[0].scrollIntoView();", footer_tag)
                time.sleep(.25)

                # SELECT THIS ROW
                select_row(n)

                # identify item on page (and confirm item was clicked)
                time.sleep(.1)
                item = d.find_element_by_class_name('ui-grid-row-focused')

                # (try to) DOWNLOAD THE FILE FOR THIS ITEM
                download_file(item, n)


            # max attempts reached for this file failed --> trigger driver re-launch
            if not config.row_done:
                raise BaseException('Base iterator failure (attempts maxed out)')
                
                        
        # outer loop will re-lanch this function starting with reset_on_idx
        except:
            config.restart_on_idx = n # index to re-start on
            print(f'  [FATAL ERROR] - scraper failed on item {config.target_fname}')
            raise TimeoutError()