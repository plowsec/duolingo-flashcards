import requests
import logging
import json
from dataclasses import dataclass, field
from typing import List
from tqdm import tqdm

from concurrent.futures import ThreadPoolExecutor

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class JsonSerializable(object):

    def to_json(self):
        return json.dumps(self.__dict__)

    def __repr__(self):
        return self.to_json()


@dataclass()
class Word(JsonSerializable):
    word: str
    related: []
    lexeme_id: str
    alternate_forms: []
    translation: []
    sentence_es: str = ""
    sentence_en: str = ""

g_proxy = "127.0.0.1:8080"
http_proxy  = f"http://{g_proxy}"
https_proxy = f"https://{g_proxy}"
ftp_proxy   = f"ftp://{g_proxy}"

g_proxies = {
            "http"  : http_proxy,
            "https" : https_proxy,
            "ftp"   : ftp_proxy
}

def parse_data(data):

    data = json.loads(data)

    words = data["vocab_overview"]
    parsed_words = []

    for word in words:
        parsed_words += [Word(word["word_string"], word["related_lexemes"], word["id"], [], [])]

    return parsed_words


def merge_duplicates(words):

    words_no_duplicate = []
    nb_duplicates = 0

    for word in words:

        for w in words_no_duplicate:

            if word.lexeme_id in w.related or w.lexeme_id in word.related:
                if word.word not in w.alternate_forms and word.word != w.word:
                    w.alternate_forms += [word.word]
                nb_duplicates += 1
                break
        else:
            words_no_duplicate += [word]

    print(nb_duplicates)
    print(len(words_no_duplicate))
    print(len(words))
    #print(words_no_duplicate)
    res = ""

    for w in words_no_duplicate:
        res += w.to_json()

    with open("toto.json", "w") as f:
        f.write(res)

    return words_no_duplicate


def collect_sentences(word: Word):

    lexeme_id = word.lexeme_id
    url = f"https://www.duolingo.com/api/1/dictionary_page?lexeme_id={lexeme_id}&use_cache=true&from_language_id=en"

    r = requests.get(url, proxies=g_proxies, verify=False)
    try:
        data = r.json()
    except:
        print(r.text)
        if "Too many requests" in r.text:
            import time
            time.sleep(1000)
            return collect_sentences(word)

    word.translation = data["translations"]
    for entry in data["alternative_forms"]:

        if entry["highlighted"]:

            word.sentence_en = entry["translation_text"]
            word.sentence_es = entry["text"]

            return word

    print("No highlighted entry found")
    print(data["alternative_forms"])
    print(url)
    word.sentence_en = data["alternative_forms"][0]["translation_text"]
    word.sentence_es = data["alternative_forms"][0]["text"]

    return word


def to_csv(word):

    res = ""

    res += word.word

    if len(word.alternate_forms) > 0:
        res += " (" + ",".join(word.alternate_forms) + ")"\

    res += "\t" + word.translation + "\t" + word.sentence_es + "\t" + word.sentence_en

    return res


if __name__ == "__main__":

    data = ""

    with open("known_words.json") as f:

        data = "\n".join(f.readlines())

    words = parse_data(data)
    no_duplicates = merge_duplicates(words)

    res = ""

    # run concurrently
    with ThreadPoolExecutor(max_workers=3) as executor:
        words_enriched = list(tqdm(executor.map(collect_sentences, no_duplicates)))

    for w in words_enriched:

        res += to_csv(w) + "\n"

    with open("data.csv", "w") as f:
        f.write(res)
