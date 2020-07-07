import requests
import json
import logging

from dataclasses import dataclass
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.DEBUG)

g_proxy = "127.0.0.1:8080"

g_proxies = {
    "http"  : f"http://{g_proxy}",
    "https" : f"https://{g_proxy}",
    "ftp"   : f"ftp://{g_proxy}"
}

"""
TODO:

Auto-detect the languages configured by the user (mother tongue and language to learn)
    * nice to have
    
Add Text-to-speech
    * Save URL
    * Download content
    * Insert into flashcard
        
Download the known words into JSON.
    * easy, add versioning?
    
Save a state of the collection (P1): then run the script periodically and generate new flash cards for the newly learned words.
    * painful: need to repopulate the "related terms" ?
    
Sort related terms:
    * Masculine singular form first
    * ??
"""


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
    gender: str
    infinitive: str
    alternate_forms: []
    translation: []
    sentence_es: str = ""
    sentence_en: str = ""


    def to_csv(self):

        res = self.word

        if len(self.alternate_forms) > 0:
            res += " (" + ",".join(self.alternate_forms) + ")"

        res += "\t" + self.translation + "\t" + self.sentence_es + "\t" + self.sentence_en

        return res


def parse_data(data):

    data = json.loads(data)

    words = data["vocab_overview"]
    parsed_words = []

    for word in words:
        parsed_words += [Word(word["word_string"], word["related_lexemes"], word["id"], word["gender"], word["infinitive"], [], [])]

    return parsed_words


# find related terms (such as feminine form of a noun) and merge them
def merge_duplicates(words):

    words_no_duplicate = []
    nb_duplicates = 0

    for word in words:

        for w in words_no_duplicate:

            # are the words references in their "related" collection?
            if word.lexeme_id in w.related or w.lexeme_id in word.related:

                # check that the word was not already added
                if word.word not in w.alternate_forms and word.word != w.word:

                    # prefer the masculine singular form over the other alternate forms
                    if w.gender is not None and "Masculine" in w.gender:

                        if word.gender is None:
                            word.gender = w.gender

                        # in case both are masculine, then one of them is the plural form
                        if "Masculine" in word.gender and len(word.word) >= len(w.word):

                            w.alternate_forms += [word.word]
                        elif "Masculine" in word.gender and len(word.word) < len(w.word):
                            w.alternate_forms += [w.word]
                            w.word = word.word
                            w.lexeme_id = word.lexeme_id
                            w.related = word.related
                        else:
                            w.alternate_forms += [word.word]

                    elif w.infinitive == w.word:
                        w.alternate_forms += [word.word]
                    else:
                        w.alternate_forms += [w.word]
                        w.word = word.word
                        w.lexeme_id = word.lexeme_id
                        w.related = word.related

                nb_duplicates += 1
                break
        else:
            words_no_duplicate += [word]

    logging.debug(f"Found {nb_duplicates} duplicates")
    logging.debug(f"Original / Filtered: {len(words)} / {len(words_no_duplicate)}")

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
            chosen_entry = entry
            break
    else:
        chosen_entry = data["alternative_forms"][0]

    # No highlighted entry found, so pick the first one.
    word.sentence_en = chosen_entry["translation_text"]
    word.sentence_es = chosen_entry["text"]
    return word


def generate_csv():

    with open("known_words.json") as f:

        data = "\n".join(f.readlines())

    words = parse_data(data)
    no_duplicates = merge_duplicates(words)
    res = ""

    # sort alternate forms so that masculine forms come first.
    custom_alphabet = ["o", "e", "a"]
    for w in no_duplicates:
        w.alternate_forms = sorted(w.alternate_forms, key=lambda x: [len(x)] + [custom_alphabet.index(c) if c in custom_alphabet else -1 for c in x])

    # run concurrently to collect the sentences and the audio files.
    with ThreadPoolExecutor(max_workers=4) as executor:
        words_enriched = list(tqdm(executor.map(collect_sentences, no_duplicates[:10])))

    # generate csv
    for w in words_enriched:

        res += w.to_csv() + "\n"

    # save final csv
    with open("data.csv", "w") as f:
        f.write(res)


if __name__ == "__main__":

    generate_csv()
