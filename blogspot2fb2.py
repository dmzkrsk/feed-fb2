from datetime import datetime
import getpass
from lxml import etree
import os
from dateutil.parser import parse
import re
import time
from urllib2 import urlopen
from html2fb2 import HtmlToFb
import logging

_logger = logging.getLogger('feed-fb2.writer')
_logger.addHandler(logging.NullHandler())

VERSION = '0.1'
PROGRAM_NAME = 'blogspot2fb v%s' % VERSION

NSFEED = {
    'a': 'http://www.w3.org/2005/Atom',
    's': 'http://a9.com/-/spec/opensearchrss/1.0/',
}

class TreeWrapper(object):

    def __init__(self, tree):
        """
        @type tree: lxml.etree._ElementTree
        """
        self.tree = tree

    def xpath(self, path):
        return self.tree.xpath(path, namespaces=NSFEED)

    def xpath_value(self, path):
        return self.tree.xpath(path, namespaces=NSFEED)[0]

    def xpath_date(self, path):
        """
        @rtype: datetime
        """
        return parse(self.xpath_value(path))

    def __getitem__(self, item):
        return self.tree.__getitem__(item)

class BloggerToBook(object):
    NSMAP = {
        None: 'http://www.gribuser.ru/xml/fictionbook/2.0',
        #'xlink': 'http://www.w3.org/1999/xlink',
    }

    def __init__(self, stream, genre, lang, **options):
        """
        @type stream: file
        @type genre: list
        @type lang: str
        """
        _logger.debug('Parsing stream')
        tree = TreeWrapper(etree.parse(stream))

        _logger.debug('Preparing header')

        self.book = etree.Element("FictionBook", nsmap=self.NSMAP)

        name = tree.xpath_value('/a:feed/a:author/a:name/text()')
        firstName, lastName = re.split('\s+', name, 1)
        email = tree.xpath_value('/a:feed/a:author/a:email/text()')
        homePage = tree.xpath_value('/a:feed/a:author/a:uri/text()')
        bookTitle= tree.xpath_value('/a:feed/a:title/text()')
        annotation= tree.xpath_value('/a:feed/a:subtitle/text()')

        bookId = tree.xpath_value('/a:feed/a:id/text()')

        sourceUrl = tree.xpath_value('/a:feed/a:link[@rel="alternate" and @type="text/html" and @href]/@href')

        date = tree.xpath_date('/a:feed/a:updated/text()')
        bookVersion = '%d' % time.mktime(date.timetuple())

        titleInfoItems = [self._e('genre', x) for x in genre]

        titleInfoItems += [
            self._e('author', None,
                self._e('first-name', firstName),
                self._e('last-name', lastName),
                self._e('home-page', homePage),
                self._e('email', email),
            ),
            self._e('book-title', bookTitle),
            self._e('annotation', None,
                self._e('p', annotation)
            ),
            self._e('date', date.strftime('%Y'), value=date.strftime("%Y-%m-%d")),
            self._e('lang', lang),
            self._e('src-lang', lang),
        ]

        description = self._e('description', None,
            self._e('title-info', None,
                *titleInfoItems
            ),
            self._e('document-info', None,
                self._e('author', None,
                    self._e('nickname', getpass.getuser()),
                ),
                self._e('program-used', PROGRAM_NAME),
                self._e('date', datetime.today().strftime("%d %B, %Y"), value=datetime.today().strftime("%Y-%m-%d")),
                self._e('src-url', sourceUrl),
                self._e('id', bookId),
                self._e('version', bookVersion),
            )
        )

        self.book.append(description)

        body = self._e('body', None,
            self._e('title', None,
                self._e('p', name),
                self._e('p', bookTitle),
            )
        )

        _logger.debug('Parsing entries')

        for entry in reversed(tree.xpath('/a:feed/a:entry')):
            entry = TreeWrapper(entry)
            title = entry.xpath_value('./a:title/text()')
            published = entry.xpath_date('./a:published/text()')

            content = entry.xpath_value('./a:content/text()')
            _logger.debug('%s %d bytes long' % (title, len(content)))
            content = etree.HTML(content)

            section = self._e('section', None,
                self._e('title', None,
                    self._e('p', title)
                ),
                self._e('subtitle', published.strftime('%d %B, %Y')
                )
            )

            for bit in HtmlToFb(content).get_tree():
                section.append(bit)

            body.append(section)

        self.book.append(body)
        _logger.debug('Book parsed')

    def _e(self, tag, content, *children, **attrib):
        e = etree.Element(tag, attrib)
        if content is not None:
            e.text = content

        for sub in children:
            e.append(sub)

        return e

    def write(self, binary_stream):
        """
        @type binary_stream: file
        """
        xml = etree.tostring(self.book, xml_declaration=True, encoding='utf-8', pretty_print=True)
        # print xml
        binary_stream.write(xml)

if __name__ == '__main__':
    import sys
    import optparse
    import logging

    parser = optparse.OptionParser()
    parser.add_option("-g", "--genre", action="append", dest='genre', default=[], help='fb2.1 genre list')
    parser.add_option("-l", "--lang", action="store", dest='lang', default='en', help='book language')

    log = logging.getLogger('feed-fb2')
    frmttr = logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s', '%Y-%m-%d %H:%M:%S')
    shdlr = logging.StreamHandler(sys.stderr)
    shdlr.setFormatter(frmttr)
    log.addHandler(shdlr)
    log.setLevel(logging.DEBUG)

    options, args = parser.parse_args()
    if not options.genre:
        options.genre = ['ref_ref']

    if os.path.exists(args[0]):
        log.info('Reading local file: %s' % args[0])
        stream = open(args[0])
    else:
        source, name = args[0].split(':', 1)
        if source == 'blogspot':
            log.info('Loading %s from blogspot' % name)
            url = 'http://%s.blogspot.com/feeds/posts/default/?max-results=0' % name
            log.info('Retirieving number of results')
            tree = etree.parse(urlopen(url))
            results = int(tree.xpath('/a:feed/s:totalResults/text()', namespaces=NSFEED)[0])
            log.info('%d items found' % results)
            log.info('Retirieving items')
            url = 'http://%s.blogspot.com/feeds/posts/default/?max-results=%d' % (name, results)
            stream = urlopen(url)
        else:
            log.error('Invalid command: %s' % source)
            stream = open(args[0])

    log.info('Parsing')
    b2b = BloggerToBook(stream, **options.__dict__)
    if args[1] == '-':
        o = sys.stdout
        log.info('Book dumped into STDOUT')
    else:
        o = open(args[1], 'wb')
        log.info('Book saved into %s' % args[1])

    b2b.write(o)
    o.close()

    log.info('Done')
