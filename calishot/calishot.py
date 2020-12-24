import os
import fire
import requests
from pathlib import Path
from urllib.parse import *
import uuid
from sqlite_utils import Database
import datetime

from bs4 import BeautifulSoup
# import browser_cookie3 


import gevent
from gevent import monkey
from gevent import Timeout
from gevent.pool import Pool
monkey.patch_socket()



class SourceStoreSqlietUtils():
    def __init__(self, dir='.'):
        self.store=init_sites_db(dir=dir)

    def save(self, site):
        save_site(self.store, site)

    def check_calibre_site(self, site):
        return check_calibre_site(self.store, site)

    def check_and_save_site(self, site):
        check_and_save_site(self.store, site)


class SourceSqlitetUtils():
    pass
    

def init_sites_db(dir="."):
    
    path = Path(dir) / "sites.db" 

    db = Database(path)
    if not "sites" in db.table_names():
        db["sites"].create({
        "uuid": str,
        "ip": str,
        "url": str,
        "type": str,
        "hostnames": str,
        "ports": str,
        "country": int,
        "isp": str,
        "version": str,
        "status": str,
        "last_online": str,
        "last_check": str,
        "error": int,
    #     "schema_version": 1
    #     # TODO: add the most common formats
        }, pk="uuid")
        # }, pk="uuid", not_null=True)

    # if not "sites" in db.table_names():
    #     db["sites"].create({
    #     "uuid": str
    #     }, pk="uuid",)

    db.table("sites", pk='uuid', batch_size=100, alter=True)
    return db


def save_site(db: Database, site):
    # # TODO: Check if the site is not alreday present
    # def save_sites(db, sites):
    #     db["sites"].insert_all(sites, alter=True,  batch_size=100)
    if not 'uuid' in site: 
        site['uuid']=str(uuid.uuid4())    
    print(site)
    db["sites"].upsert(site, pk='uuid')

# import pysnooper
# @pysnooper.snoop()
def check_calibre_site(site):
    ret={}
    ret['uuid']=site["uuid"]
    now=str(datetime.datetime.now())
    ret['last_check']=now 

    api=site['url']+'/ajax/'
    timeout=15
    library=""
    url=api+'search'+library+'?num=0'
    print()
    print("Getting ebooks count:", site['url'])
    print(url)
    
    try:
        r=requests.get(url, verify=False, timeout=(timeout, 30))
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        r.status_code
        ret['error']=r.status_code
        if (r.status_code == 401):
            ret['status']="unauthorized"
        else:
            ret['status']="down"
        return ret
    except requests.RequestException as e: 
        print("Unable to open site:", url)
        # print (getattr(e, 'message', repr(e)))
        print (e)
        ret['status']="down"
        return ret
    except Exception as e:
        print ("Other issue:", e)
        ret['status']='Unknown Error'
        print (e)
        return ret
    except :
        print("Wazza !!!!")
        ret['status']='Critical Error'
        print (e)
        return ret

    print("Total count=",r.json()["total_num"])

    ret['type']="calibre-server"    
    status=ret['status']='online'
    if status=="online":
        ret['last_online']=now 

    return ret


def check_and_save_site(db, site):
        res= check_calibre_site(site)
        print(res)
        save_site(db, res)

def get_site_uuid_from_url(db, url):

    site=urlparse(url)
    hostname=site.hostname
    site=site._replace(path='')
    
    url=urlunparse(site)
    # print (url)

    # print (hostname)
    row=db.conn.execute(f"select * from sites where instr(hostnames, '{hostname}')").fetchone()
    # print(row)
    if row:
        return row

        
def get_site_uuid_from_url(db, url):

    site=urlparse(url)
    hostname=site.hostname
    site=site._replace(path='')
    
    url=urlunparse(site)
    # print (url)

    # print (hostname)
    row=db.conn.execute(f"select * from sites where instr(hostnames, '{hostname}')").fetchone()
    # print(row)
    if row:
        return row

        


def map_site_from_url(url):
    ret={}

    site=urlparse(url)

    print(site)
    site=site._replace(path='')
    ret['url']=urlunparse(site)
    ret['hostnames']=[site.hostname] 
    ret['ports']=[str(site.port)]

    return ret


def import_urls_from_file(filepath, dir='.'):

    db=init_sites_db(dir)

    with open(filepath) as f:
        for url in f.readlines():
            url=url.rstrip()
            # url='http://'+url
            if get_site_uuid_from_url(db, url):
                print(f"'{url}'' already present")
                continue
            print(f"'{url}'' added")
            save_site(db, map_site_from_url(url))
    


def get_libs_from_site(site):

    server=site.rstrip('/')
    api=server+'/ajax/'
    timeout=30
    
    print()
    print("Server:", server)
    url=api+'library-info'

    print()
    print("Getting libraries from", server)
    # print(url)

    try:
        r=requests.get(url, verify=False, timeout=(timeout, 30))
        r.raise_for_status()
    except requests.RequestException as e: 
        print("Unable to open site:", url)
        return
    except Exception as e:
        print ("Other issue:", e)
        return
        # pass

    libraries = r.json()["library_map"].keys()
    print("Libraries:", ", ".join(libraries))
    return libraries

def check_calibre_list(dir='.'):    
    db=init_sites_db(dir)
    sites=[]
    for row in db["sites"].rows:
        print(f"Queueing:{row['url']}")
        sites.append(row)
    print(sites)
    pool = Pool(100)
    pool.map(lambda s: check_and_save_site (db, s), sites)

def map_site_from_shodan_api(site):
    ret={}
    if not 'http' in site:
        return
    # if 'calibre ' in site['http']['server']:
    #     return
    # ret['type']="calibre-server"
    ret['ip']= site['ip_str']
    ret['ports']=[site['port']]
    ret['country']= site['location']['country_code']
    ret['isp']= site['isp']
    ret['hostnames']= site['hostnames']
    ret['version']= site['http']['server'].lstrip('calibre ')
    return ret


def get_calibres_from_shodan(query='calibre', offset=1, limit=10, max_page=0, dir='.', key=os.environ.get("SHODAN_API_KEY")):
    # TODO: Error counter on Shodan
    # query='"Server: calibre" http.status%3A200'
    # TODO: handle request exception correctly and make a function : https://stackoverflow.com/questions/16511337/correct-way-to-try-except-using-python-requests-module
    page=0
    count=0
    total=0

    db=init_sites_db(dir)

    while True:
        if (max_page and page==max_page):
            break
        page+=1

        # url=f'https://api.shodan.io/shodan/host/search?query={query}&minify=True&limit={limit}&key={key}'
        url=f'https://api.shodan.io/shodan/host/search?query={query}&minify=True&limit={limit}&key={key}&offset={offset}'
        print(url)
        try:
            r=requests.get(url, timeout=(100, 100))
            r.raise_for_status()
        except requests.RequestException as e: 
            print("Unable to contact Shodan", url)
            print (e.response)
            print (r.text)
            print (e)
            print (r.status_code)
            continue
            # pass
        except Exception as e:
            print ("Other issue:", e)
            continue
            # pass
        except :
            print("Wazza !!!!")
            continue

        try:
            total=r.json()['total']
            j_sites=r.json()['matches']
        except:
            print("Bad content !!!!")
            print(r.text)
            cntinue

        # try:
        #     total=r.json()['total']
        #     print ("total:", total)
        # except KeyError:
        #     print("Shodan ERROR")
        #     print(r.text)
        #     continue

        sites=[]
        for u in j_sites:
            d_site=map_site_from_shodan_api(u)
            if(d_site):
                print(d_site)
                sites.append(d_site)
                save_site(db, d_site)
        # save_sites(db,sites)

        count=len(r.json()['matches'])
        offset+=count
        if (offset>=total):
            break

    print("Total count=",r.json()["total_num"])

    ret['type']="calibre-server"    
    status=ret['status']='online'
    if status=="online":
        ret['last_online']=now 

    return ret


#  open -a "Google Chrome" --args --user-data-dir=browser_cookie3 
def scrape_calibres_from_shodan():
    cj = browser_cookie3.firefox(domain_name='www.shodan.io')
    session = requests.Session()
    # session.headers.update({'User-Agent': 'Chrome/79.0.3945.117'})
    user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'
    headers = {'User-Agent': user_agent}
    # url="https://www.shodan.io/search?query=%22Server%3A+calibre%22+http.status%3A200+country%3A%22FR%22"
    # url="https://github.com/"
    # url="https://www.shodan.io/search?query=%22Server%3A+calibre%22+http.status%3A200+country%3A%22FR%22"
    url="https://www.shodan.io/"
    r = session.get(url,headers=headers, cookies=cj)
    url="https://www.shodan.io/search?query=%22Server%3A+calibre%22+http.status%3A200"
    r = session.get(url,headers=headers, cookies=cj)
    # url="https://www.shodan.io/search?query=%22Server%3A+calibre%22+http.status%3A200+country%3A%22FR%22"
    soup=BeautifulSoup(r.text, 'lxml')
    # print ( soup.prettify())
    for link in soup.findAll('a'):
        href=str(link.get('href'))
        print(href)


if __name__ == "__main__":
    fire.Fire({
        "scan-shodan": get_calibres_from_shodan,
        "scrape-shodan":scrape_calibres_from_shodan,
        "import": import_urls_from_file,
        "check":check_calibre_list,
        "check-site":check_calibre_site,


        })

# example of a fts search sqlite-utils index.db "select * from summary_fts where summary_fts  match 'title:fre*'"