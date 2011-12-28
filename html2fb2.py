# coding=utf-8
from lxml import etree
from lxml.sax import saxify
from xml.sax import ContentHandler
import re

class BaseCheck(object):
    ATTR = None
    BLOCK_TAGS = ['th', 'td', 'table', 'tr', 'p']

    def __init__(self, stackable):
        self.stackable = stackable

    def top_stack(self, qname):
        if not self.stackable.stack:
            parent = self.stackable.new_root('p')
        else:
            parent = self.stackable.stack[-1]

        # Если в родителе уже есть такой элемент не отделенный тектом, то не грех
        # использовать его
        if qname not in self.BLOCK_TAGS and len(parent) and parent[-1].tag == qname and not parent[-1].tail:
            element = parent[-1]
        else:
            element = etree.Element(qname)
            element.text = ''
            element.tail = ''
            parent.append(element)

        self.stackable.stack.append(element)

    def checker(self, qname, styles):
        raise NotImplementedError()

    def process(self, qname, styles):
        if self.checker(qname, styles) and not self.stack_find(self.ATTR):
            self.top_stack(self.ATTR)
            self.stackable.stack_usage.append((qname, self.ATTR))

    def stack_find(self, what):
        return self.stackable.stack_find(what)

class Strong(BaseCheck):
    ATTR = 'strong'

    @classmethod
    def no_lighter(cls, styles):
        t = styles.get('font-weight', None)
        if not t:
            return True

        try:
            v = int(t)
            return v >= 500
        except ValueError:
            return t != 'lighter' and t != 'normal'

    @classmethod
    def heavy(cls, styles):
        t = styles.get('font-weight', None)
        if not t:
            return False

        try:
            v = int(t)
            return v >= 500
        except ValueError:
            return t == 'bolder' or t == 'bold'

    def checker(self, qname, styles):
        return (
                 (qname == 'strong' or qname == 'b') and self.no_lighter(styles)
              ) or self.heavy(styles)

class Emphasis(BaseCheck):
    ATTR = 'emphasis'

    @classmethod
    def emphasis(cls, styles):
        t = styles.get('font-style', None)
        if not t:
            return False

        return 'italics' in t

    @classmethod
    def no_normal(cls, styles):
        t = styles.get('font-style', None)
        if not t:
            return True

        return 'normal' not in t

    def checker(self, qname, styles):
        return (
                 (qname == 'em' or qname == 'i') and self.no_normal(styles)
              ) or self.emphasis(styles)

class StrikeThrough(BaseCheck):
    ATTR = 'strikethrough'

    @classmethod
    def strikethrough(cls, styles):
        t = styles.get('font-style', None)
        if not t:
            return False

        return 'strikethrough' in t

    @classmethod
    def no_normal(cls, styles):
        t = styles.get('font-style', None)
        if not t:
            return True

        return 'normal' not in t

    def checker(self, qname, styles):
        return (
                   (qname == 'del' or qname == 's') and self.no_normal(styles)
                   ) or self.strikethrough(styles)

class BasicCheck(BaseCheck):
    EXTRA = []

    def checker(self, qname, styles):
        return qname == self.ATTR or qname in self.EXTRA

class SubScript(BasicCheck):
    ATTR = 'sub'

class SupScript(BasicCheck):
    ATTR = 'sup'

class Code(BasicCheck):
    ATTR = 'code'
    EXTRA = ['kbd']

class Paragraph(BasicCheck):
    ATTR = 'p'
    EXTRA = ['div', 'body']

    def process(self, qname, styles):
        if self.checker(qname, styles) and not self.stack_find('table'):
            self.stackable.new_root('p')
            self.stackable.stack_usage.append((qname, None))

class Table(BasicCheck):
    ATTR = 'table'

    def process(self, qname, styles):
        if self.checker(qname, styles) and not self.stack_find('table'):
            self.stackable.new_root('table')
            self.stackable.stack_usage.append((qname, self.ATTR))

class TableObject(BasicCheck):
    WITHIN = None

    def process(self, qname, styles):
        if self.checker(qname, styles) and self.stack_find(self.WITHIN):
            self.top_stack(self.ATTR)
            self.stackable.stack_usage.append((qname, self.ATTR))

class TableRow(TableObject):
    ATTR = 'tr'
    WITHIN = 'table'

class TableCell(TableObject):
    ATTR = 'td'
    WITHIN = 'tr'

class TableHeading(TableObject):
    ATTR = 'th'
    WITHIN = 'tr'

class HtmlToFb(ContentHandler):
    STYLE = re.compile('\s*([a-z\-]+)\s*:\s*(.+?)\s*(?:;|$)')
    BLANKS = re.compile('^(\s*)(.*?)(\s*)$', re.MULTILINE)
    MAX_BREAKS = 2
    BLOCKS = ['td', 'th']

    def __init__(self, content):
        ContentHandler.__init__(self)

        self.content = False
        self.tree = []
        self.stack = []
        self.stack_usage = []

        self.strong = False
        self.emphasis = False

        saxify(content, self)

    def get_tree(self):
        if not len(self.tree):
            return []

        #последний параграф мог быть добавлен фиктивно
        #поэтому автоматически он не очистится
        assert 0 <= len(self.stack) <= 1
        if self.stack:
            self.stack_removed(self.stack[0], True)

        last = self.tree[-1]
        if self.empty(last):
            self.tree.pop(-1)

        return self.tree

    @classmethod
    def empty(cls, bit):
        return not bit.text and not len(bit)

    def stack_find(self, what):
        return any(v == what for _k, v in self.stack_usage)

    @classmethod
    def empty_tag(cls, tag):
        e = etree.Element(tag)
        e.text = ''
        e.tail = ''
        return e

    def new_root(self, qname):
        if len(self.tree) and self.empty(self.tree[-1]):
            element = self.tree[-1]
            if qname == element.tag:
                assert len(self.stack) == 0  or (len(self.stack) == 1 and self.stack[0] == element)
                assert 0 <= len(self.stack_usage) <= 1, self.stack_usage
            else:
                self.tree.pop(-1)
                element = None
        else:
            element = None

        if element is None:
            element = self.empty_tag(qname)
            self.tree.append(element)
            self.clear_stack()

        self.stack = [element]
        self.stack_usage = []

        self.breakCount = 0
        return element

    def clear_stack(self):
        """
        Проверяем существующий стек и удаляем пустые узлы
        Стек можно изменять, он все равно будет переписан
        """
        removed = None

        while len(self.stack):
            bit = self.stack[-1]
            if self.empty(bit):
                removed = self.stack.pop(-1)
                # не посылаем сигнал об изъятии со стека
                # так как потом эти элементы будут удалены из дерева полностью
            else:
                break

        if removed is not None and len(self.stack):
            self.stack[-1].remove(removed)

    @classmethod
    def append_to(cls, e, c):
        if len(e):
            e[-1].tail += c
        else:
            e.text += c

    def characters(self, content):
        if not self.content:
            return

        if self.stack:
            element = self.stack[-1]
        else:
            element = self.new_root('p')

        if self.breakCount:
            if not content.startswith(' '):
                content = ' ' + content
            self.breakCount = 0

        if self.no_text_yet():
            content = content.lstrip()

        # крайние пробелы попробуем вытащить из тегов

        # если это пробелы в параграфе, то вытаскивать их некуда
        if len(self.stack) == 1:
            self.append_to(element, content)
            return

        m = self.BLANKS.match(content)
        # разделяем
        fore, content, back = m.groups()

        # пробелы слева кидаем или в хвост сиблинга родителя слева
        # или в текст корня
        if fore:
            prev = self.stack[1].getprevious()
            if prev is None:
                p = self.find_non_empty_parent()
                if not p.text.endswith(' '):
                    p.text += ' '
            else:
                if not prev.tail.endswith(' '):
                    prev.tail += ' '

        # контент как обычно
        self.append_to(element, content)

        # пробелы пихаем в свой хвост
        if back and not element.tag in self.BLOCKS and not element.tail.endswith(' '):
            element.tail += ' '

    def find_non_empty_parent(self):
        for element in reversed(self.stack):
            if element.text:
                return element

        return self.stack[0]

    def no_text_yet(self):
        # Блочные элементы не передают пробелы родителям
        if self.stack[-1].tag in self.BLOCKS:
            return not bool(self.stack[-1].text)

        if len(self.stack[-1]):
            return False

        for element in self.stack:
            if element.text:
                return False
            if element.getprevious() is not None:
                return False

        return True

    def endElementNS(self, name, qname):
        if qname == 'body':
            self.content = False

        if not self.content:
            return

        if self.stack_usage and qname == self.stack_usage[-1][0]:
            child = self.stack.pop(-1)
            self.stack_removed(child, not bool(self.stack))
            self.stack_usage.pop(-1)

            # Если верхушка стека была пустой, то удалимся также и из родительского элемента
            # Если на стеке больше ничего нет, то пустой элемент удалится при создании нового блока
            if len(self.stack) and self.empty(child):
                self.stack[-1].remove(child)

    @classmethod
    def stack_removed(cls, element, is_last):
        #переносим хвостовой пробел у последнего потомка себе
        if len(element):
            tail = element[-1].tail
            element[-1].tail = element[-1].tail.rstrip()
        elif element.text:
            tail = element.text
            element.text = element.text.rstrip()
        else:
            return

        if not is_last and tail.endswith(' ') and not element.tail.endswith(' '):
            element.tail += ' '

    def startElementNS(self, name, qname, attrs):
        if qname == 'body':
            self.content = True

        if not self.content:
            return

        styles = dict(self.STYLE.findall(attrs.get((None, 'style'), '').lower()))

        Paragraph(self).process(qname, styles)

        Strong(self).process(qname, styles)
        Emphasis(self).process(qname, styles)
        StrikeThrough(self).process(qname, styles)
        SupScript(self).process(qname, styles)
        SubScript(self).process(qname, styles)
        Code(self).process(qname, styles)

        Table(self).process(qname, styles)
        TableRow(self).process(qname, styles)
        TableHeading(self).process(qname, styles)
        TableCell(self).process(qname, styles)

        if qname == 'br':
            self.breakCount += 1
            if self.breakCount >= self.MAX_BREAKS and not self.stack_find(Table.ATTR):
                self.breakCount = 0
                # Копируем стек
                if len(self.stack):
                    new_stack = [self.empty_tag(t.tag) for t in self.stack]
                    for parent, child in zip(new_stack[:-1], new_stack[1:]):
                        parent.append(child)

                    self.clear_stack()
                    # Если стек очистился полностью, то можно и удалить из дерева
                    # Обычно это происходит в new_root
                    if not len(self.stack):
                        self.tree.pop(-1)

                    self.tree.append(new_stack[0])
                    self.stack = new_stack

if __name__ == '__main__':
    stp = ['font-weight: bold', ' font-weight  :bold  ', 'font-weight: bold ;\ncolor: red']
    for x in stp:
        print HtmlToFb.STYLE.findall(x)

    data = [
        (u'hello world', u'<p>hello world</p>'),
        (u'<p>Hi</p><div>xis</div><p>Meeh</p>', u'<p>Hi</p>\n<p>xis</p>\n<p>Meeh</p>'),
        (u'Masta <p>Get</p> Out!', u'<p>Masta</p>\n<p>Get</p>\n<p>Out!</p>'),
        (u'Masta <span>Get</span> Out!', u'<p>Masta Get Out!</p>'),
        (u'Masta <img /> Out!', u'<p>Masta  Out!</p>'),
        (u'Masta <b>GGG</b> Out!', u'<p>Masta <strong>GGG</strong> Out!</p>'),
        (u'Masta <span style="font-weight: bold">GGG</span> Out!', u'<p>Masta <strong>GGG</strong> Out!</p>'),
        (u'Masta <span style="font-weight: normal">GGG</span> Out!', u'<p>Masta GGG Out!</p>'),
        (u'Masta <b>G</b>G<b>G</b> Out!', u'<p>Masta <strong>G</strong>G<strong>G</strong> Out!</p>'),
        (u'Masta <b><i>GGG</i></b> Out!', u'<p>Masta <strong><emphasis>GGG</emphasis></strong> Out!</p>'),
        (u'Masta <i><b><i>GGG</i></b></i> Out!', u'<p>Masta <emphasis><strong>GGG</strong></emphasis> Out!</p>'),
        (u'Masta <b><b>GGG</b></b> Out!', u'<p>Masta <strong>GGG</strong> Out!</p>'),

        (u'<sup>a</sup>', u'<p><sup>a</sup></p>'),
        (u'<sub>a</sub>', u'<p><sub>a</sub></p>'),
        (u'<kbd>a</kbd>', u'<p><code>a</code></p>'),
        (u'<code>a</code>', u'<p><code>a</code></p>'),
        (u'<s>a</s>', u'<p><strikethrough>a</strikethrough></p>'),
        (u'<del>a</del>', u'<p><strikethrough>a</strikethrough></p>'),

        (u'<p><b> ololo </b></p>', u'<p><strong>ololo</strong></p>'),

        (u'<p><b>mama roma </b><b> pizza time</b></p>', u'<p><strong>mama roma</strong> <strong>pizza time</strong></p>'),
        (u'<p><b>mama roma </b><b>pizza time</b></p>', u'<p><strong>mama roma</strong> <strong>pizza time</strong></p>'),
        (u'<p>django<b><i> oooo </i>cute </b>power!</p>', u'<p>django <strong><emphasis>oooo</emphasis> cute</strong> power!</p>'),
        (u'<p>django<b><i> oooo </i>cute</b>power!</p>', u'<p>django <strong><emphasis>oooo</emphasis> cute</strong>power!</p>'),
        (u'<p>django<b><i> oooo </i><s>cute </s></b>power!<b>beatch</b></p>',
            u'<p>django <strong><emphasis>oooo</emphasis> <strikethrough>cute</strikethrough></strong> power!<strong>beatch</strong></p>'),
        (u'<p>django<b><i> oooo </i><s>cute </s></b>power!</p>',
            u'<p>django <strong><emphasis>oooo</emphasis> <strikethrough>cute</strikethrough></strong> power!</p>'),
        (u'<p>django<b><i> oooo </i></b>power!</p>',
            u'<p>django <strong><emphasis>oooo</emphasis></strong> power!</p>'),

        (u'<p> </p>', u''),
        (u' ', u''),

        (u'<b></b> <b>33</b> <b></b>', u'<p><strong>33</strong></p>'),
        (u'<b>3</b> <b>3</b> <b></b>', u'<p><strong>3</strong> <strong>3</strong></p>'),
        (u'<b></b> <b>3</b> <b>3</b>', u'<p><strong>3</strong> <strong>3</strong></p>'),
        (u'<b></b><b>33</b><b></b>', u'<p><strong>33</strong></p>'),
        (u'<b>33 </b><b></b>', u'<p><strong>33</strong></p>'),
        (u'<b>33</b><b> </b>', u'<p><strong>33</strong></p>'),
        (u'<b>3</b><b>3</b><b></b>', u'<p><strong>33</strong></p>'),
        (u'<b></b><b>3</b><b>3</b>', u'<p><strong>33</strong></p>'),
        (u'<p><b>3<i> aa</i></b></p>', u'<p><strong>3 <emphasis>aa</emphasis></strong></p>'),
        (u'<p><b>3<i> aa </i>3</b></p>', u'<p><strong>3 <emphasis>aa</emphasis> 3</strong></p>'),
        (u'<p><b>3<br/>3</b></p>', u'<p><strong>3 3</strong></p>'),
        (u'<p><b></b></p>33', u'<p>33</p>'),
        (u'<p>33 </p><p> 33</p>', u'<p>33</p>\n<p>33</p>'),

        (u'<p><b><br/>33</b></p>', u'<p><strong>33</strong></p>'),
        (u'<p><br/><b>33</b></p>', u'<p><strong>33</strong></p>'),
        (u'<p><b><br/><i>33</i></b></p>', u'<p><strong><emphasis>33</emphasis></strong></p>'),

        (u'<p><br/></p>', u''),

        (u'<p<br/><b></b><b> </b><b></b><b>33</b><b></b><b> </b><br/><b></b><b> </b><b> </b><b>33</b><b></b><b></b><b>33</b> <b>33</b> <b></b> </p>', u'<p><strong>33</strong> <strong>3333</strong> <strong>33</strong></p>'),

        (u'<p>33</p><table><tr><td> 33</td></tr></table>', u'<p>33</p>\n<table><tr><td>33</td></tr></table>'),
        (u'<p>33</p><table><tr><td> 33</td><td> 33 </td><td>33 </td><td> 33</td></tr></table>', u'<p>33</p>\n<table><tr><td>33</td><td>33</td><td>33</td><td>33</td></tr></table>'),
        (u'<p>33</p><table><tr><td><br/>33</td></tr></table>', u'<p>33</p>\n<table><tr><td>33</td></tr></table>'),

        (u'<div><a href="http://www.amazon.de"><img border="0" src="https://images-na.ssl-images-amazon.com" /></a><br /><b>AAA</b><br /><b><br /></b><br /><br /><a name="more"></a><br /></div></div><br /><div></div><div><span><span lang="EN-US">A Dance with Dragons Review</span></span></div>',
           u'<p><strong>AAA</strong></p>\n<p>A Dance with Dragons Review</p>'),

        (u'<p><b>12</b><b><br /><br /></b></p>', u'<p><strong>12</strong></p>'),
        (u'<p><b>12</b><b><br /></b><br /><br /></p>', u'<p><strong>12</strong></p>'),
        (u'<p><b>12</b><b>2<br /><br /></b></p>', u'<p><strong>122</strong></p>'),
        (u'<p><b>12</b><b>2<br /><br />2</b></p>', u'<p><strong>122</strong></p>\n<p><strong>2</strong></p>'),
        (u'<p><b>12</b><b><br /><br />2</b></p>', u'<p><strong>12</strong></p>\n<p><strong>2</strong></p>'),

        (u'My table:<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr><tr><td><b>3</b></td><td><i>4</i></td></tr></table>Done!',
         u'<p>My table:</p>\n<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr><tr><td><strong>3</strong></td><td><emphasis>4</emphasis></td></tr></table>\n<p>Done!</p>'),

        (u'<p><table><tr><td>1</td></tr></table></p>', u'<table><tr><td>1</td></tr></table>'),
        (u'<table><tr><td><p>1</p></td></tr></table></p>', u'<table><tr><td>1</td></tr></table>'),
        (u'<table><tr><td><p><b>1</b></p><em>2</em></td></tr></table></p>', u'<table><tr><td><strong>1</strong><emphasis>2</emphasis></td></tr></table>'),

        (u'Masta<br/><br/>Out!', u'<p>Masta</p>\n<p>Out!</p>'),
        (u'<p>Mama<i>Pizza<b>TTT<br/><br/>Me</b>To</i></p>', u'<p>Mama<emphasis>Pizza<strong>TTT</strong></emphasis></p>\n<p><emphasis><strong>Me</strong>To</emphasis></p>'),
        (u'<p>Mama<i>Pizza<b>TTT<br/><br/></b>To</i></p>', u'<p>Mama<emphasis>Pizza<strong>TTT</strong></emphasis></p>\n<p><emphasis>To</emphasis></p>'),
        (u'Masta<br/>xx<br/>Out!', u'<p>Masta xx Out!</p>'),
        (u'<table><tr><td>x<br/>y</td></tr></table>', u'<table><tr><td>x y</td></tr></table>'),
        (u'<table><tr><td>x<br/><br/>y</td></tr></table>', u'<table><tr><td>x y</td></tr></table>'),
        (u'<table><tr><td></td></tr></table>', u''),
        (u'<p></p><p>2</p><p></p>', u'<p>2</p>'),

        (u'<table><tr><td>aa<em>cc</em>bb</td></tr></table>', u'<table><tr><td>aa<emphasis>cc</emphasis>bb</td></tr></table>'),
    ]

    for source, expected in data:
        print 'SOURCE:', source
        xml = etree.HTML(source)
        if xml is None:
            print 'PARSED: <None>'
            xml = ''
            p = '<None>'
        else:
            print 'PARSED:', etree.tostring(xml, encoding=unicode)
            xml_tree = HtmlToFb(xml).get_tree()
            p = '\\n'.join(etree.tostring(t, encoding=unicode) for t in xml_tree)
            xml = '\n'.join(etree.tostring(t, encoding=unicode) for t in xml_tree)
        print 'RESULT:', p
        assert xml == expected, [xml, expected]
        print
