# ELIZA + DOCTOR script in Python

# MIT License
#
# Tobias Thelen, 2022
# based on code by Copyright (c) 2019 Wade Brainerd (MIT Licence, see https://github.com/wadetb/eliza )
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import logging
import random
import re
from collections import namedtuple

# Fix Python2/Python3 incompatibility
try:
    input = raw_input
except NameError:
    pass

log = logging.getLogger(__name__)


class Key:
    """Holds data for a single keyword with weight and decompositions."""
    def __init__(self, word, weight, decomps):
        self.word = word
        self.weight = weight
        self.decomps = decomps


class Decomp:
    """Holds data for a single decomposition, attached to a key."""
    def __init__(self, parts, save, reasmbs):
        self.parts = parts
        self.save = save
        self.reasmbs = reasmbs
        self.next_reasmb_index = 0


class Eliza:
    """The ELIZA algorithm an a parser for scripts."""

    def __init__(self):
        self.initials = []
        self.finals = []
        self.quits = []
        self.pres = {}
        self.posts = {}
        self.synons = {}
        self.keys = {}
        self.memory = []

    def load(self, script):
        """Parses a script, passed as a string."""
        key = None
        decomp = None
        for line in script.splitlines():
            if not line.strip():
                continue
            tag, content = [part.strip() for part in line.split(':')]
            if tag == 'initial':
                self.initials.append(content)
            elif tag == 'final':
                self.finals.append(content)
            elif tag == 'quit':
                self.quits.append(content)
            elif tag == 'pre':
                parts = content.split(' ')
                self.pres[parts[0]] = parts[1:]
            elif tag == 'post':
                parts = content.split(' ')
                self.posts[parts[0]] = parts[1:]
            elif tag == 'synon':
                parts = content.split(' ')
                self.synons[parts[0]] = parts
            elif tag == 'key':
                parts = content.split(' ')
                word = parts[0]
                weight = int(parts[1]) if len(parts) > 1 else 1
                key = Key(word, weight, [])
                self.keys[word] = key
            elif tag == 'decomp':
                parts = content.split(' ')
                save = False
                if parts[0] == '$':
                    save = True
                    parts = parts[1:]
                decomp = Decomp(parts, save, [])
                key.decomps.append(decomp)
            elif tag == 'reasmb':
                parts = content.split(' ')
                decomp.reasmbs.append(parts)

    def _match_decomp_r(self, parts, words, results):
        """Recursive method for mathcing decompositions."""
        if not parts and not words:
            return True
        if not parts or (not words and parts != ['*']):
            return False
        if parts[0] == '*':
            for index in range(len(words), -1, -1):
                results.append(words[:index])
                if self._match_decomp_r(parts[1:], words[index:], results):
                    return True
                results.pop()
            return False
        elif parts[0].startswith('@'):
            root = parts[0][1:]
            if not root in self.synons:
                raise ValueError("Unknown synonym root {}".format(root))
            if not words[0].lower() in self.synons[root]:
                return False
            results.append([words[0]])
            return self._match_decomp_r(parts[1:], words[1:], results)
        elif parts[0].lower() != words[0].lower():
            return False
        else:
            return self._match_decomp_r(parts[1:], words[1:], results)

    def _match_decomp(self, parts, words):
        results = []
        if self._match_decomp_r(parts, words, results):
            return results
        return None

    def _next_reasmb(self, decomp):
        index = decomp.next_reasmb_index
        result = decomp.reasmbs[index % len(decomp.reasmbs)]
        decomp.next_reasmb_index = index + 1
        return result

    def _reassemble(self, reasmb, results):
        output = []
        for reword in reasmb:
            if not reword:
                continue
            if reword[0] == '(' and reword[-1] == ')':
                index = int(reword[1:-1])
                if index < 1 or index > len(results):
                    raise ValueError("Invalid result index {}".format(index))
                insert = results[index - 1]
                for punct in [',', '.', ';']:
                    if punct in insert:
                        insert = insert[:insert.index(punct)]
                output.extend(insert)
            else:
                output.append(reword)
        return output

    def _sub(self, words, sub):
        output = []
        for word in words:
            word_lower = word.lower()
            if word_lower in sub:
                output.extend(sub[word_lower])
            else:
                output.append(word)
        return output

    def _match_key(self, words, key):
        """Check all decompositions for a given input and a given keyword"""
        for decomp in key.decomps:
            results = self._match_decomp(decomp.parts, words)
            if results is None:
                log.debug('Decomp did not match: %s', decomp.parts)
                continue
            log.debug('Decomp matched: %s', decomp.parts)
            log.debug('Decomp results: %s', results)
            results = [self._sub(words, self.posts) for words in results]
            log.debug('Decomp results after posts: %s', results)
            reasmb = self._next_reasmb(decomp)
            log.debug('Using reassembly: %s', reasmb)
            if reasmb[0] == 'goto':
                goto_key = reasmb[1]
                if not goto_key in self.keys:
                    raise ValueError("Invalid goto key {}".format(goto_key))
                log.debug('Goto key: %s', goto_key)
                return self._match_key(words, self.keys[goto_key])
            output = self._reassemble(reasmb, results)
            if decomp.save:
                self.memory.append(output)
                log.debug('Saved to memory: %s', output)
                continue
            return output
        return None

    def respond(self, text):
        """Create an output for a given input passed as a string."""
        if text.lower() in self.quits:
            return None

        text = re.sub(r'\s*\.+\s*', ' . ', text)  # separate dots from text ("Yes." -> "Yes . ")
        text = re.sub(r'\s*,+\s*', ' , ', text)  # separate commas from text
        text = re.sub(r'\s*;+\s*', ' ; ', text)  # separate semicolons from text
        log.debug('After punctuation cleanup: %s', text)

        words = [w for w in text.split(' ') if w]  # split input into single words (only keep nonempty words)
        log.debug('Input: %s', words)

        words = self._sub(words, self.pres)  # preprocessing
        log.debug('After pre-substitution: %s', words)

        # find all keys that match a word in the input
        keys = [self.keys[w.lower()] for w in words if w.lower() in self.keys]
        # sort the keys with descending weights
        keys = sorted(keys, key=lambda k: -k.weight)
        log.debug('Sorted keys: %s', [(k.word, k.weight) for k in keys])

        output = None

        for key in keys:
            output = self._match_key(words, key)
            if output:
                log.debug('Output from key: %s', output)
                break
        if not output:
            if self.memory:
                index = random.randrange(len(self.memory))
                output = self.memory.pop(index)
                log.debug('Output from memory: %s', output)
            else:
                output = self._next_reasmb(self.keys['xnone'].decomps[0])
                log.debug('Output from xnone: %s', output)

        return " ".join(output)

    def initial(self):
        return random.choice(self.initials)

    def final(self):
        return random.choice(self.finals)

    def run(self):
        print(self.initial())

        while True:
            sent = input('> ')

            output = self.respond(sent)
            if output is None:
                break

            print(output)

        print(self.final())


# The DOCTOR script (with minor additions from the AI lecture)
doctor="""
initial: How do you do.  Please tell me your problem.
final: Goodbye.  Thank you for talking to me.
quit: bye
quit: goodbye
quit: quit
pre: dont don't
pre: cant can't
pre: wont won't
pre: recollect remember
pre: dreamt dreamed
pre: dreams dream
pre: maybe perhaps
pre: how what
pre: when what
pre: certainly yes
pre: machine computer
pre: computers computer
pre: were was
pre: you're you are
pre: i'm i am
pre: same alike
post: am are
post: your my
post: me you
post: myself yourself
post: yourself myself
post: i you
post: you I
post: my your
post: i'm you are
synon: belief feel think believe wish
synon: family mother mom father dad sister brother wife children child
synon: desire want need
synon: sad unhappy depressed sick
synon: happy elated glad better
synon: cannot can't
synon: everyone everybody nobody noone
synon: be am is are was
key: xnone
  decomp: *
    reasmb: I'm not sure I understand you fully.
    reasmb: Please go on.
    reasmb: What does that suggest to you ?
    reasmb: Do you feel strongly about discussing such things ?
key: sorry
  decomp: *
    reasmb: Please don't apologise.
    reasmb: Apologies are not necessary.
    reasmb: I've told you that apologies are not required.
key: apologise
  decomp: *
    reasmb: goto sorry
key: remember 5
  decomp: * i remember *
    reasmb: Do you often think of (2) ?
    reasmb: Does thinking of (2) bring anything else to mind ?
    reasmb: What else do you recollect ?
    reasmb: Why do you recollect (2) just now ?
    reasmb: What in the present situation reminds you of (2) ?
    reasmb: What is the connection between me and (2) ?
  decomp: * do you remember *
    reasmb: Did you think I would forget (2) ?
    reasmb: Why do you think I should recall (2) now ?
    reasmb: What about (2) ?
    reasmb: goto what
    reasmb: You mentioned (2) ?
key: if 3
  decomp: * if *
    reasmb: Do you think its likely that (2) ?
    reasmb: Do you wish that (2) ?
    reasmb: What do you know about (2) ?
    reasmb: Really, if (2) ?
key: dreamed 4
  decomp: * i dreamed *
    reasmb: Really, (2) ?
    reasmb: Have you ever fantasized (2) while you were awake ?
    reasmb: Have you ever dreamed (2) before ?
    reasmb: goto dream
key: dream 3
  decomp: *
    reasmb: What does that dream suggest to you ?
    reasmb: Do you dream often ?
    reasmb: What persons appear in your dreams ?
    reasmb: Do you believe that dreams have something to do with your problems ?
key: perhaps
  decomp: *
    reasmb: You don't seem quite certain.
    reasmb: Why the uncertain tone ?
    reasmb: Can't you be more positive ?
    reasmb: You aren't sure ?
    reasmb: Don't you know ?
key: name 15
  decomp: *
    reasmb: I am not interested in names.
    reasmb: I've told you before, I don't care about names -- please continue.
key: deutsch
  decomp: *
    reasmb: goto xforeign
    reasmb: I told you before, I don't understand German.
key: francais
  decomp: *
    reasmb: goto xforeign
    reasmb: I told you before, I don't understand French.
key: italiano
  decomp: *
    reasmb: goto xforeign
    reasmb: I told you before, I don't understand Italian.
key: espanol
  decomp: *
    reasmb: goto xforeign
    reasmb: I told you before, I don't understand Spanish.
key: xforeign
  decomp: *
    reasmb: I speak only English.
key: hello
  decomp: *
    reasmb: How do you do.  Please state your problem.
    reasmb: Hi.  What seems to be your problem ?
key: computer 50
  decomp: *
    reasmb: Do computers worry you ?
    reasmb: Why do you mention computers ?
    reasmb: What do you think machines have to do with your problem ?
    reasmb: Don't you think computers can help people ?
    reasmb: What about machines worrys you ?
    reasmb: What do you think about machines ?
key: am
  decomp: * am i *
    reasmb: Do you believe you are (2) ?
    reasmb: Would you want to be (2) ?
    reasmb: Do you wish I would tell you you are (2) ?
    reasmb: What would it mean if you were (2) ?
    reasmb: goto what
  decomp: *
    reasmb: Why do you say 'am' ?
    reasmb: I don't understand that.
key: are
  decomp: * are you *
    reasmb: Why are you interested in whether I am (2) or not ?
    reasmb: Would you prefer if I weren't (2) ?
    reasmb: Perhaps I am (2) in your fantasies.
    reasmb: Do you sometimes think I am (2) ?
    reasmb: goto what
  decomp: * are *
    reasmb: Did you think they might not be (2) ?
    reasmb: Would you like it if they were not (2) ?
    reasmb: What if they were not (2) ?
    reasmb: Possibly they are (2) .
key: your
  decomp: * your *
    reasmb: Why are you concerned over my (2) ?
    reasmb: What about your own (2) ?
    reasmb: Are you worried about someone else's (2) ?
    reasmb: Really, my (2) ?
key: was 2
  decomp: * was i *
    reasmb: What if you were (2) ?
    reasmb: Do you think you were (2) ?
    reasmb: Were you (2) ?
    reasmb: What would it mean if you were (2) ?
    reasmb: What does (2) suggest to you ?
    reasmb: goto what
  decomp: * i was *
    reasmb: Were you really ?
    reasmb: Why do you tell me you were (2) now ?
    reasmb: Perhaps I already know you were (2) .
  decomp: * was you *
    reasmb: Would you like to believe I was (2) ?
    reasmb: What suggests that I was (2) ?
    reasmb: What do you think ?
    reasmb: Perhaps I was (2) .
    reasmb: What if I had been (2) ?
key: i
  decomp: * i @desire *
    reasmb: What would it mean to you if you got (3) ?
    reasmb: Why do you want (3) ?
    reasmb: Suppose you got (3) soon ?
    reasmb: What if you never got (3) ?
    reasmb: What would getting (3) mean to you ?
    reasmb: What does wanting (3) have to do with this discussion ?
  decomp: * i am * @sad *
    reasmb: I am sorry to hear that you are (3) .
    reasmb: Do you think that coming here will help you not to be (3) ?
    reasmb: I'm sure it's not pleasant to be (3) .
    reasmb: Can you explain what made you (3) ?
  decomp: * i am * @happy *
    reasmb: How have I helped you to be (3) ?
    reasmb: Has your treatment made you (3) ?
    reasmb: What makes you (3) just now ?
    reasmb: Can you explan why you are suddenly (3) ?
  decomp: * i was *
    reasmb: goto was
  decomp: * i @belief * i *
    reasmb: Do you really think so ?
    reasmb: But you are not sure you (3) .
    reasmb: Do you really doubt you (3) ?
  decomp: * i * @belief * you *
    reasmb: goto you
  decomp: * i am *
    reasmb: Is it because you are (2) that you came to me ?
    reasmb: How long have you been (2) ?
    reasmb: Do you believe it is normal to be (2) ?
    reasmb: Do you enjoy being (2) ?
  decomp: * i @cannot *
    reasmb: How do you think that you can't (3) ?
    reasmb: Have you tried ?
    reasmb: Perhaps you could (3) now.
    reasmb: Do you really want to be able to (3) ?
  decomp: * i don't *
    reasmb: Don't you really (2) ?
    reasmb: Why don't you (2) ?
    reasmb: Do you wish to be able to (2) ?
    reasmb: Does that trouble you ?
  decomp: * do i feel *
    reasmb: Tell me more about such feelings.
    reasmb: Do you often feel (2) ?
    reasmb: Do you enjoy feeling (2) ?
    reasmb: Of what does feeling (2) remind you ?
  decomp: * i * you *
    reasmb: Perhaps in your fantasies we (2) each other.
    reasmb: Do you wish to (2) me ?
    reasmb: You seem to need to (2) me.
    reasmb: Do you (2) anyone else ?
  decomp: *
    reasmb: You say (1) ?
    reasmb: Can you elaborate on that ?
    reasmb: Do you say (1) for some special reason ?
    reasmb: That's quite interesting.
key: you
  decomp: * you remind me of *
    reasmb: goto alike
  decomp: * you are *
    reasmb: What makes you think I am (2) ?
    reasmb: Does it please you to believe I am (2) ?
    reasmb: Do you sometimes wish you were (2) ?
    reasmb: Perhaps you would like to be (2) .
  decomp: * you * me *
    reasmb: Why do you think I (2) you ?
    reasmb: You like to think I (2) you -- don't you ?
    reasmb: What makes you think I (2) you ?
    reasmb: Really, I (2) you ?
    reasmb: Do you wish to believe I (2) you ?
    reasmb: Suppose I did (2) you -- what would that mean ?
    reasmb: Does someone else believe I (2) you ?
  decomp: * you *
    reasmb: We were discussing you -- not me.
    reasmb: Oh, I (2) ?
    reasmb: You're not really talking about me -- are you ?
    reasmb: What are your feelings now ?
key: yes
  decomp: *
    reasmb: You seem to be quite positive.
    reasmb: You are sure.
    reasmb: I see.
    reasmb: I understand.
key: no
  decomp: *
    reasmb: Are you saying no just to be negative?
    reasmb: You are being a bit negative.
    reasmb: Why not ?
    reasmb: Why 'no' ?
key: my 2
  decomp: $ * my *
    reasmb: Lets discuss further why your (2) .
    reasmb: Earlier you said your (2) .
    reasmb: But your (2) .
    reasmb: Does that have anything to do with the fact that your (2) ?
  decomp: * my * @family *
    reasmb: Tell me more about your family.
    reasmb: Who else in your family (4) ?
    reasmb: Your (3) ?
    reasmb: What else comes to mind when you think of your (3) ?
  decomp: * my *
    reasmb: Your (2) ?
    reasmb: Why do you say your (2) ?
    reasmb: Does that suggest anything else which belongs to you ?
    reasmb: Is it important that your (2) ?
key: can
  decomp: * can you *
    reasmb: You believe I can (2) don't you ?
    reasmb: goto what
    reasmb: You want me to be able to (2) .
    reasmb: Perhaps you would like to be able to (2) yourself.
  decomp: * can i *
    reasmb: Whether or not you can (2) depends on you more than me.
    reasmb: Do you want to be able to (2) ?
    reasmb: Perhaps you don't want to (2) .
    reasmb: goto what
key: what
  decomp: *
    reasmb: Why do you ask ?
    reasmb: Does that question interest you ?
    reasmb: What is it you really wanted to know ?
    reasmb: Are such questions much on your mind ?
    reasmb: What answer would please you most ?
    reasmb: What do you think ?
    reasmb: What comes to mind when you ask that ?
    reasmb: Have you asked such questions before ?
    reasmb: Have you asked anyone else ?
key: because
  decomp: *
    reasmb: Is that the real reason ?
    reasmb: Don't any other reasons come to mind ?
    reasmb: Does that reason seem to explain anything else ?
    reasmb: What other reasons might there be ?
key: why
  decomp: * why don't you *
    reasmb: Do you believe I don't (2) ?
    reasmb: Perhaps I will (2) in good time.
    reasmb: Should you (2) yourself ?
    reasmb: You want me to (2) ?
    reasmb: goto what
  decomp: * why can't i *
    reasmb: Do you think you should be able to (2) ?
    reasmb: Do you want to be able to (2) ?
    reasmb: Do you believe this will help you to (2) ?
    reasmb: Have you any idea why you can't (2) ?
    reasmb: goto what
  decomp: *
    reasmb: goto what
key: everyone 2
  decomp: * @everyone *
    reasmb: Realy, (2) ?
    reasmb: Surely not (2) .
    reasmb: Can you think of anyone in particular ?
    reasmb: Who, for example?
    reasmb: Are you thinking of a very special person ?
    reasmb: Who, may I ask ?
    reasmb: Someone special perhaps ?
    reasmb: You have a particular person in mind, don't you ?
    reasmb: Who do you think you're talking about ?
key: everybody 2
  decomp: *
    reasmb: goto everyone
key: nobody 2
  decomp: *
    reasmb: goto everyone
key: noone 2
  decomp: *
    reasmb: goto everyone
key: always 1
  decomp: *
    reasmb: Can you think of a specific example ?
    reasmb: When ?
    reasmb: What incident are you thinking of ?
    reasmb: Really, always ?
key: alike 10
  decomp: *
    reasmb: In what way ?
    reasmb: What resemblance do you see ?
    reasmb: What does that similarity suggest to you ?
    reasmb: What other connections do you see ?
    reasmb: What do you suppose that resemblence means ?
    reasmb: What is the connection, do you suppose ?
    reasmb: Could here really be some connection ?
    reasmb: How ?
key: like 10
  decomp: * @be * like *
    reasmb: goto alike
key: ai 99
  decomp: * hate *   
    reasmb: Oh. But do you like ELIZA?
  decomp: *
    reasmb: There's more to a machine than man might think.
    reasmb: Does the possibility of artificial intelligence scare you?
"""


def main():
    eliza = Eliza()  # initialize ELIZA
    eliza.load(doctor)  # use the doctor script given above
    eliza.run()  # prompt for inputs, create output until a quitting phrase occured

if __name__ == '__main__':
    logging.basicConfig()
    main()
