import sys
import os
import time
import re
import shutil
import requests
import json
import fire
from humanize import naturalsize as hsize
import humanize
from langid.langid import LanguageIdentifier, model
import iso639
import time
import json

from requests.adapters import HTTPAdapter
import urllib.parse
import urllib3
from pathlib import Path
import uuid
from sqlite_utils import Database

import gevent
from gevent import monkey
from gevent import Timeout
from gevent.pool import Pool
monkey.patch_socket()
# monkey.patch_all()

from calishot import init_sites_db, get_libs_from_site

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
identifier = LanguageIdentifier.from_modelstring(model, norm_probs=True)

def get_site_db(uuid, dir):
        f_uuid=str(uuid)+".db"
        print(f_uuid)
        path = Path(dir) / str(f_uuid) 
        return Database(path)


def init_site_db(site, _uuid="", dir="."):
    
    if not _uuid:
        s_uuid=str(uuid.uuid4())
    else:
        s_uuid=str(_uuid)

    f_uuid=s_uuid+".db"
    path = Path(dir) / f_uuid 
    db = Database(path)

    
    if not "site" in db.table_names():
        s=db["site"]
        s.insert(
            {    
                "uuid": s_uuid,
                "urls": [site],
                "schema_version": 1
            }
        )


    if not "ebooks" in db.table_names():
        db["ebooks"].create({
        "uuid": str,
        "id": int,
        "library": str,  #TODO: manage libraries ids as integer to prevent library renam on remote site  
        "title": str,
        "authors": str,
        "series": str,
        "series_index": int,
        # "edition": int, 
        "language": str,
        "desc": str,
        "identifiers": str,
        "tags": str,
        "publisher": str,
        "pubdate": str,
        "last_modified": str,
        "timestamp": str,
        "formats": str,
        "cover": int,
        # "epub": int,
        # "mobi": int,
        # "pdf": int,
        # TODO: add the most common formats to avoid alter tables
        }, pk="uuid")

    if not "libraries" in db.table_names():
        db["libraries"].create({
        "id": int,    
        "names": str
        }, pk="id")


        # db.table("ebooks", pk="id")
        # db.table("ebooks", pk="id", alter=True

    return db


def get_format_url(db, book, format):
    url=json.loads(db['site'].get(1)['urls'])[0]
    library=book['library']
    id_=str(book['id'])

    f_url = url+"/get/"+format+"/"+id_+"/"+library
    return f_url
    

    
def get_desc_url(db, book):
    url=json.loads(db['site'].get(1)['urls'])[0]
    library=book['library']
    id_=str(book['id'])

    f_urls=[]
    d_url =url+"#book_id="+id_+"&library_id="+library+"&panel=book_details"
    return d_url


def save_books_metadata_from_site(db, books):
    uuid=db["site"].get(1)["uuid"]
    # print(uuid)
    
    ebooks_t=db["ebooks"]


    # print([c[1] for c in ebooks_t.columns])
    # for b in books:
    #     print(b['title'])
    #     ebooks_t.insert(b, alter=True)

    # ebooks_t.insert_all(books, alter=True)
    ebooks_t.insert_all(books, alter=True,  pk='uuid', batch_size=1000)
    # print([c[1] for c in ebooks_t.columns])

def load_metadata(dir, uuid):
    pass

def update_done_status(book):
    source=book['source']
    if source['status']!='ignored':
        if set(source['formats'].keys()) == set(book['formats']) & set(source['formats'].keys()):
            book['source']['status']="done"
        else: 
            book['source']['status']="todo"

def index_site_list_seq(file):
    with open(file) as f:
        for s in f.readlines():
            try: 
                index_ebooks(s.rstrip())
            except:
                continue

def index_site_list(file):
    pool = Pool(40)

    with open(file) as f:
        sites = f.readlines()
        sites= [s.rstrip() for s in sites]
        print(sites)
        pool.map(index_ebooks_except, sites)

def index_ebooks_except(site):
    try:
        index_ebooks(site)
    except:
        print("Error on site")

def index_ebooks(site, library="", start=0, stop=0, dir=".", num=1000, force_refresh=False):

    #TODO old calibres don't manage libraries.  /ajax/library-info endpoint doesn't exist. It would be better to manage calibre version directly 

    libs=[]
    try:
        libs= get_libs_from_site(site)
    except:
        print("old lib")
        
    _uuid=str(uuid.uuid4())
    
    if libs:
        for lib in libs:
            index_ebooks_from_library(site=site, _uuid=_uuid, library=lib, start=start, stop=stop, dir=dir, num=num, force_refresh=force_refresh)   
    else:
            index_ebooks_from_library(site=site, _uuid=_uuid, start=start, stop=stop, dir=dir, num=num, force_refresh=force_refresh)   

def index_ebooks_from_library(site, _uuid="", library="", start=0, stop=0, dir=".", num=1000, force_refresh=False):
    
    offset= 0 if not start else start-1
    num=min(1000, num)
    server=site.rstrip('/')
    api=server+'/ajax/'
    lib=library
    library= '/'+library if library else library

    timeout=15

    print(f"\nIndexing library: {lib} from server: {server} ")
    url=api+'search'+library+'?num=0'
    print(f"\nGetting ebooks count of library: {lib} from server:{server} ")
    # print(url)
    
    try:
        r=requests.get(url, verify=False, timeout=(timeout, 30))
        r.raise_for_status()
    except requests.RequestException as e: 
        print("Unable to open site:", url)
        return
        # pass
    except Exception as e:
        print ("Other issue:", e)
        return
        # pass
    except :
        print("Wazza !!!!")
        sys.exit(1)
        

    total_num=int(r.json()["total_num"])
    total_num= total_num if not stop else stop
    print()    
    print(f"Total count={total_num} from {server}")
 
    # library=r.json()["base_url"].split('/')[-1]
    # base_url=r.json()["base_url"]

    db=init_site_db(site, _uuid=_uuid, dir=dir)

    print()

    range=offset+1
    while offset < total_num:
        remaining_num = min(num, total_num - offset)
        # print()
        # print("Downloading ids: offset="+str(offset), "num="+str(remaining_num))
        print ('\r {:180.180}'.format(f'Downloading ids: offset={str(offset)} count={str(remaining_num)} from {server}'), end='')

        # url=server+base_url+'?num='+str(remaining_num)+'&offset='+str(offset)+'&sort=timestamp&sort_order=desc'
        url=api+'search'+library+'?num='+str(remaining_num)+'&offset='+str(offset)+'&sort=timestamp&sort_order=desc'

        # print("->", url)
        try:
            r=requests.get(url, verify=False, timeout=(timeout, 30))
            r.raise_for_status()
        except requests.RequestException as e: 
            print ("Connection issue:", e)
            return
            # pass
        except Exception as e:
            print ("Other issue:", e)
            return
            # pass
        except :
            print ("Wazza !!!!")
            return
        # print("Ids received from:"+str(offset), "to:"+str(offset+remaining_num-1))
        
        # print()
        # print("Downloading metadata from", str(offset+1), "to", str(offset+remaining_num))
        print ('\r {:180.180}'.format(f'Downloading metadata from {str(offset+1)} to {str(offset+remaining_num)}/{total_num} from {server}'), end='')
        books_s=",".join(str(i) for i in r.json()['book_ids'])
        url=api+'books'+library+'?ids='+books_s
        # url=server+base_url+'/books?ids='+books_s
        # print("->", url)
        # print ('\r{:190.190}'.format(f'url= {url} ...'), end='')

        try:
            r=requests.get(url, verify=False, timeout=(60, 60))
            r.raise_for_status()
        except requests.RequestException as e: 
            print ("Connection issue:", e)
            return
            # pass
        except Exception as e:
            print ("Other issue:", e)
            return
            # pass
        except :
            print ("Wazza !!!!")
            return
        # print(len(r.json()), "received")
        print ('\r {:180.180}'.format(f'{len(r.json())} received'), end='')
        
        
        books=[]
        for id, r_book in r.json().items():                
                uuid=r_book['uuid']
                if not uuid:
                    print ("No uuid for ebook: ignored")
                    continue 


                if r_book['authors']:
                    desc= f"({r_book['title']} / {r_book['authors'][0]})"
                else:
                    desc= f"({r_book['title']})"

                # print (f'\r--> {range}/{total_num} - {desc}', end='')
                # print (f'\r{server}--> {range}/{total_num} - {desc}', end='')
                print ('\r {:180.180} '.format(f'{range}/{total_num} ({server} : {uuid} --> {desc}'), end='')


                if not force_refresh:
                    # print("Checking local metadata:", uuid)
                    try:
                        book = load_metadata(dir, uuid)
                    except:
                        print("Unable to get metadata from:", uuid)
                        range+=1
                        continue
                    if book:
                        print("Metadata already present for:", uuid)
                        range+=1
                        continue

                if not r_book['formats']:
                    # print("No format found for {}".format(r_book['uuid']))
                    range+=1
                    continue


                book={}
                book['uuid']=r_book['uuid']
                book['id']=id
                book['library']=lib
                book['title']=r_book['title']
                book['authors']=r_book['authors']
                # book['desc']=""
                book['desc']=r_book['comments']
                book['series']=r_book['series']
                s_i=r_book['series_index']
                if (s_i): 
                    book['series_index']=int(s_i)
                # book['edition']=0
                book['identifiers']=r_book['identifiers']
                book['tags']=r_book['tags']
                book['publisher']=r_book['publisher']
                book['pubdate']=r_book['pubdate']

                if not r_book['languages']:
                # if True:
                    text=r_book['title']+". "
                    if r_book['comments']:
                        text=r_book['comments']                    
                    s_language, prob=identifier.classify(text)
                    if prob >= 0.85:
                        language =  iso639.to_iso639_2(s_language)
                        book['language']=language
                    else:
                        book['language']=''
                else:
                    book['language']=iso639.to_iso639_2(r_book['languages'][0])

                if r_book['cover']:
                    book['cover']= True
                else:
                    book['cover']= False

                book['last_modified']=r_book['last_modified']
                book['timestamp']=r_book['timestamp']

                book['formats']=[]
                formats=r_book['formats']
                for f in formats:                    
                    if 'size' in r_book['format_metadata'][f]:
                        size=int(r_book['format_metadata'][f]['size'])
                    else:
                        # print()
                        # print(f"Size not found for format '{f}'  uuid={uuid}: skipped")
                        pass
                        #TODO query the size when the function to rebuild the full url is ready
                        #   
                        # print("Trying to get size online: {}".format('url'))
                        # try:
                        #     size=get_file_size(s['url'])
                        # except:
                        #     print("Unable to access size for format '{}' : {} skipped".format(f, uuid))
                        #     continue
                    book[f]=(size)
                    book['formats'].append(f)

                if not book['formats']:
                # if not c_format:
                    # print()
                    # print(f"No format found for {book['uuid']} id={book['id']} : skipped")
                    range+=1
                    # continue

                books.append(book)
                range+=1

        # print()
        # print("Saving metadata")
        print ('\r {:180.180}'.format(f'Saving metadata from {server}'), end='')
        save_books_metadata_from_site(db, books)
        print('\r {:180.180}'.format(f'--> Saved {range-1}/{total_num} ebooks from {server}'), end='')
        print()
        print()

        # try:
        #     save_metadata(db, books)
        # except:
        #     print("Unable to save book metadata")

        offset=offset+num
    

    

def query(query_str="", dir="."):
    dbs=[]
    for path in os.listdir(dir):
        db = Database(path)
        # print (db["ebooks"].count)
        # for row in db["site"].rows:
        #     print (f'{row["urls"]}: {db["ebooks"].count}')
        # db["ebooks"].search(query_str)
        # url=db['site'].get(1)['urls'][0]
        url=db['site'].get(1)
        print (url)

        for ebook in db["ebooks"].rows_where(query_str):
            # print (f"{ebook['title']} ({ebook['uuid']})")
            print (ebook)

def search(query_str, dir=".", links_only=False):
    path = Path(dir) / "index.db" 
    db_index = Database(path)
    # table=db_index["summary"]
    # rows=table.search(query_str)
    # print(rows)
    sites=set()
    ebook_ids=[]
    for ebook in db_index["summary"].search(query_str):
        sites.add(ebook[-1])
        ebook_ids.append((ebook[3], ebook[-1]))
        # print (ebook)
    # print("sites:", sites) 
    # print("ebooks:", ebook_ids) 

    site_dbs={}
    for s in sites:
        f_uuid=s+".db"
        path = Path(dir) / f_uuid 
        site_dbs[s]=Database(path)
        # print(site_dbs[s].tables)
    
    for e in ebook_ids:
        # ebook=site_dbs[e[1]]["ebooks"].get(e[0])
        # print("ebook:", ebook)
        db=site_dbs[e[1]] 
        # ebooks=db.conn.execute("select * from ebooks").fetchone()
        ebook=db.conn.execute(f'select * from ebooks where uuid="{e[0]}"').fetchone()
        url=json.loads(db['site'].get(1)['urls'])[0]
        library=db['site'].get(1)['library']
        formats=json.loads(ebook[14])
        id_=str(ebook[0])

        if not links_only:
            print()
            print("Title:", ebook[2])
            print("Author:", ebook[3])
            print("Serie:", ebook[4])
            print("Formats:", formats)

        for f in formats:
            print(url+"get/"+f+"/"+id_+"/"+library)


def get_stats(dir="."):
    dbs=[]
    size=0
    count=0
    for f in os.listdir(dir):
        if not f.endswith(".db"):
            continue
        if f == "index.db":
            continue
        path = Path(dir) / f 
        dbs.append(Database(path))

    for db in dbs:
        for i, ebook in enumerate(db["ebooks"].rows):
            uuid=ebook['uuid']
            title=ebook['title']
            formats=json.loads(ebook['formats'])
            # print(formats)
            for f in formats:
                if f in ebook:
                    if ebook[f]:
                        size+=ebook[f]
                        count+=1
                        # print (f'\r{count} {f} --> {uuid}: {title}', end ='')
                        # print (f'\r{count} : {uuid} --> {f}', end='')
                        print (f'\r{count} formats - ebook : {uuid}', end='')

    print()
    print("Total count of formats:", humanize.intcomma(count)) 
    print("Total size:", hsize(size)) 


    print()

def init_index_db(dir="."):
    
    path = Path(dir) / "index.db" 
    
    db_index = Database(path)
    if not "summary" in db_index.table_names():
        db_index["summary"].create({
        "uuid": str,
        "title": str,
        # "source": str
        "authors": str,
        "year": str,
        "series": str,
        "language": str,
        "links": str,
        # "desc": str,
        "publisher": str,
        "tags": str,
        "identifiers": str,
        "formats": str
        }
        # )
        , pk="uuid")

        # db_index.table("index", pk="uuid")
        # db_index.table("summary").enable_fts(["title"])
        # db_index["summary"].enable_fts(["title", "authors", "series", "uuid", "language", "identifiers", "tags", "publisher", "formats", "pubdate"])
        db_index["summary"].enable_fts(["title", "authors", "series", "language", "identifiers", "tags", "publisher", "formats", "year"])

    return db_index


def build_index (dir='.'):

    dbs=[]
    for f in os.listdir(dir):
        if not f.endswith(".db"):
            continue
        if f in ("index.db", "sites.db"):
            continue
        path = Path(dir) / f 
        dbs.append(Database(path))
    
    db_index = init_index_db(dir=dir)
    index_t=db_index["summary"]

    batch_size=10000
    count=0
    summaries=[]

    for db in dbs:
        for i, ebook in enumerate(db["ebooks"].rows):
            # print("ebook=", ebook)
            if ebook['language'] == "eng":
                continue 
            
            if ebook['authors']: 
                ebook['authors']=formats=json.loads(ebook['authors'])
            # if ebook['series']:    
            #     ebook['series']=formats=json.loads(ebook['series'])
            if ebook['identifiers']:
                ebook['identifiers']=formats=json.loads(ebook['identifiers'])
            if ebook['tags']: 
                ebook['tags']=formats=json.loads(ebook['tags'])
            ebook['formats']=formats=json.loads(ebook['formats'])
            ebook['links']=""
            summary = {k: v for k, v in ebook.items() if k in ("uuid","title", "authors", "series", "language", "formats", "tags", "publisher", "identifiers")}
            # summary = {k: v for k, v in ebook.items() if k in ("uuid","title", "authors", "series", "identifiers", "language", "tags", "publisher", "formats")}
            summary['title']={'href': get_desc_url(db, ebook), 'label': ebook['title']}

            formats=[]
            for f in ebook['formats']:
                formats.append({'href': get_format_url(db, ebook, f), 'label': f})
            summary['links']=formats
            
            pubdate=ebook['pubdate'] 
            summary['year']=pubdate[0:4] if pubdate else "" 
            summaries.append(summary)
            # print(summary)
            count+=1
            print (f"\r{count} - ebook handled: {ebook['uuid']}", end='')

            if not count % batch_size:
                # print()
                # print(f"Saving summary by batch: {len(summaries)}")    
                # print(summaries)
                # index_t.upsert_all(summaries, batch_size=1000, pk='uuid')
                # index_t.insert_all(summaries, batch_size=1000, pk='uuid')
                try:
                    index_t.insert_all(summaries, batch_size=batch_size)
                except Exception as e:
                    # dump = [(s['uuid'],s['links']) for s in summaries]
                    # print(dump)
                    print()
                    print("UUID collisions. Probalbly a site duplicate")
                    print(e)
                    print()

                    # index_t.upsert_all(summaries, batch_size=batch_size, pk='uuid')
                    # TODO Some ebooks could be missed. We need to compute the batch list, insert new ebooks and update the site index

                # print("Saved")
                # print()
                summaries=[]

    # print()
    # print("saving summary")    
    # index_t.upsert_all(summaries, batch_size=1000, pk='uuid')
    # index_t.insert_all(summaries, batch_size=1000, pk='uuid')
    try:
        index_t.insert_all(summaries, batch_size=batch_size)
    except:
        print("sqlite3.IntegrityError: UNIQUE constraint failed: summary.uuid")

    # print("summary done")
    # print()
    
    print()
    print("fts")
    index_t.populate_fts(["title", "authors", "series", "identifiers", "language", "tags", "publisher", "formats", "year"])
    print("fts done")


if __name__ == "__main__":
    fire.Fire()