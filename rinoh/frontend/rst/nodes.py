# This file is part of RinohType, the Python document preparation system.
#
# Copyright (c) Brecht Machiels.
#
# Use of this source code is subject to the terms of the GNU Affero General
# Public License v3. See the LICENSE file or http://www.gnu.org/licenses/.


import re
import unicodedata

from datetime import datetime

import rinoh as rt

from . import (DocutilsInlineNode, DocutilsNode,
               DocutilsBodyNode, DocutilsBodySubNode,
               DocutilsGroupingNode)
from ...dimension import DimensionUnit, INCH, CM, MM, PT, PICA, PERCENT
from ...util import intersperse


# TODO: support for the following nodes is still missing
# (http://docutils.sourceforge.net/docs/ref/doctree.html)
# - abbreviation
# - acronym
# - container
# - decoration / header / footer
# - math / math_block
# - pending
# - substitution_reference


class Text(DocutilsInlineNode):
    node_name = '#text'

    def styled_text(self):
        return self.text


class Inline(DocutilsInlineNode):
    pass


class Document(DocutilsBodyNode):
    pass


class DocInfo(DocutilsBodyNode):
    def build_flowable(self):
        doc_info = {field.name: field.value for field in self.getchildren()}
        return rt.SetMetadataFlowable(**doc_info)


# bibliographic elements

class DocInfoField(DocutilsInlineNode):
    @property
    def name(self):
        return self.tag_name

    @property
    def value(self):
        return self.styled_text()


class Author(DocInfoField):
    pass


class Authors(DocInfoField):
    @property
    def value(self):
        return [author.styled_text() for author in self.author]


class Copyright(DocInfoField):
    pass


class Address(DocInfoField):
    pass


class Organization(DocInfoField):
    pass


class Contact(DocInfoField):
    pass


class Date(DocInfoField):
    @property
    def value(self):
        try:
            return datetime.strptime(self.node.astext(), '%Y-%m-%d')
        except ValueError:
            return super().value


class Version(DocInfoField):
    pass


class Revision(DocInfoField):
    pass


class Status(DocInfoField):
    pass


# FIXME: the meta elements are removed from the docutils doctree
class Meta(DocutilsBodyNode):
    MAP = {'keywords': 'keywords',
           'description': 'subject'}

    def build_flowable(self):
        metadata = {self.MAP[self.get('name')]: self.get('content')}
        return rt.SetMetadataFlowable(**metadata)


# body elements

class System_Message(DocutilsBodyNode):
    def build_flowable(self):
        return rt.WarnFlowable(self.text)


class Comment(DocutilsInlineNode, DocutilsBodyNode):
    def build_styled_text(self):
        return None

    def build_flowable(self):
        return rt.DummyFlowable()


class Topic(DocutilsGroupingNode):
    style = 'topic'

    def _process_topic(self, topic_type):
        topic = super().build_flowable(style=topic_type)
        del topic.children[0]
        return rt.SetMetadataFlowable(**{topic_type: topic})

    def build_flowable(self):
        classes = self.get('classes')
        if 'contents' in classes:
            if 'local' in classes:
                flowables = [rt.TableOfContents(local=True)]
                try:
                    flowables.insert(0, self.title.flowable())
                except AttributeError:
                    pass
                return rt.StaticGroupedFlowables(flowables,
                                                 style='table of contents')
            else:
                toc_id, = self.get('ids')
                return rt.SetMetadataFlowable(toc_id=toc_id)
        elif 'dedication' in classes:
            return self._process_topic('dedication')
        elif 'abstract' in classes:
            return self._process_topic('abstract')
        else:
            return super().build_flowable()


class Rubric(DocutilsBodyNode):
    def build_flowable(self):
        return rt.Paragraph(self.process_content(), style='rubric')


class Sidebar(DocutilsGroupingNode):
    def build_flowable(self):
        grouped_flowables = super().build_flowable()
        return rt.Framed(grouped_flowables, style='sidebar')


class Section(DocutilsGroupingNode):
    grouped_flowables_class = rt.Section


class Paragraph(DocutilsBodyNode):
    def build_flowable(self):
        return rt.Paragraph(super().process_content())


class Compound(DocutilsGroupingNode):
    pass


class Title(DocutilsBodyNode):
    def build_flowable(self):
        if isinstance(self.parent, Document):
            return rt.SetMetadataFlowable(title=self.process_content())
        elif isinstance(self.parent, Section):
            try:
                kwargs = dict(custom_label=self.generated.build_styled_text())
            except AttributeError:
                kwargs = dict()
            return rt.Heading(self.process_content(), **kwargs)
        else:
            return rt.Paragraph(self.process_content(), style='title')


class Subtitle(DocutilsBodyNode):
    def build_flowable(self):
        return rt.SetMetadataFlowable(subtitle=self.process_content())


class Admonition(DocutilsGroupingNode):
    def flowable(self):
        return rt.Framed(super().flowable(), style='admonition')


class AdmonitionBase(DocutilsGroupingNode):
    title = None

    def flowable(self):
        title_par = rt.Paragraph(self.title, style='title')
        content = rt.StaticGroupedFlowables([title_par, super().flowable()])
        framed = rt.Framed(content, style='admonition')
        framed.admonition_type = self.__class__.__name__.lower()
        return framed


class Attention(AdmonitionBase):
    title = 'Attention!'


class Caution(AdmonitionBase):
    title = 'Caution!'


class Danger(AdmonitionBase):
    title = '!DANGER!'


class Error(AdmonitionBase):
    title = 'Error'


class Hint(AdmonitionBase):
    title = 'Hint'


class Important(AdmonitionBase):
    title = 'Important'


class Note(AdmonitionBase):
    title = 'Note'


class Tip(AdmonitionBase):
    title = 'Tip'


class Warning(AdmonitionBase):
    title = 'Warning'


class Generated(DocutilsInlineNode):
    def styled_text(self):
        return None

    def build_styled_text(self):
        return self.process_content()


class Emphasis(DocutilsInlineNode):
    def build_styled_text(self):
        return rt.SingleStyledText(self.text, style='emphasis')


class Strong(DocutilsInlineNode):
    def build_styled_text(self):
        return rt.SingleStyledText(self.text, style='strong')


class Title_Reference(DocutilsInlineNode):
    def build_styled_text(self):
        return rt.SingleStyledText(self.text, style='title reference')


class Literal(DocutilsInlineNode):
    def build_styled_text(self):
        return rt.SingleStyledText(self.text, style='monospaced')


class Superscript(DocutilsInlineNode):
    def build_styled_text(self):
        return rt.Superscript(self.process_content())


class Subscript(DocutilsInlineNode):
    def build_styled_text(self):
        return rt.Subscript(self.process_content())


class Problematic(DocutilsBodyNode, DocutilsInlineNode):
    def build_styled_text(self):
        return rt.SingleStyledText(self.text, style='error')

    def build_flowable(self):
        return rt.DummyFlowable()


class Literal_Block(DocutilsBodyNode):
    def build_flowable(self):
        text = self.text.replace(' ', unicodedata.lookup('NO-BREAK SPACE'))
        return rt.Paragraph(text, style='literal')


class Block_Quote(DocutilsGroupingNode):
    style = 'block quote'


class Attribution(Paragraph):
    def build_flowable(self):
        return rt.Paragraph('\N{EM DASH}' + self.process_content(),
                            style='attribution')


class Line_Block(DocutilsGroupingNode):
    style = 'line block'


class Line(DocutilsBodyNode):
    def build_flowable(self):
        return rt.Paragraph(self.process_content() or '\n',
                            style='line block line')


class Doctest_Block(DocutilsBodyNode):
    def build_flowable(self):
        text = self.text.replace(' ', unicodedata.lookup('NO-BREAK SPACE'))
        return rt.Paragraph(text, style='literal')


class Reference(DocutilsBodyNode, DocutilsInlineNode):
    def build_styled_text(self):
        if self.get('refid'):
            link = rt.NamedDestinationLink(self.get('refid'))
            style = 'internal link'
        elif self.get('refuri'):
            link = rt.HyperLink(self.get('refuri'))
            style = 'external link'
        else:
            return rt.MixedStyledText(self.process_content(),
                                      style='broken link')
        return rt.AnnotatedText(self.process_content(), link, style=style)

    def build_flowable(self):
        children = self.getchildren()
        assert len(children) == 1
        return self.image.flowable()


class Footnote(DocutilsBodyNode):
    def flowable(self):
        return rt.RegisterNote(super().flowable())

    def build_flowable(self):
        return rt.Note(rt.StaticGroupedFlowables(self.children_flowables(1)))


class Label(DocutilsBodyNode):
    def build_flowable(self):
        return rt.DummyFlowable()


class Footnote_Reference(DocutilsInlineNode):
    style = 'footnote'

    def build_styled_text(self):
        return rt.NoteMarkerByID(self['refid'],
                                 custom_label=self.process_content(),
                                 style=self.style)


class Citation(Footnote):
    pass


class Citation_Reference(Footnote_Reference):
    style = 'citation'


class Substitution_Definition(DocutilsBodyNode):
    def build_flowable(self):
        return rt.DummyFlowable()


class Target(DocutilsBodyNode, DocutilsInlineNode):
    def build_styled_text(self):
        # TODO: what about refid?
        try:
            destination = rt.NamedDestination(self.get('ids')[0])
            return rt.AnnotatedText(self.process_content(), destination)
        except IndexError:
            return self.process_content()   # TODO: use refname?

    def build_flowable(self):
        return rt.DummyFlowable()   # TODO: body targets


class Enumerated_List(DocutilsBodyNode):
    def build_flowable(self):
        # TODO: handle different numbering styles
        return rt.List([item.flowable() for item in self.list_item],
                       style='enumerated')


class Bullet_List(DocutilsBodyNode):
    def build_flowable(self):
        try:
            return rt.List([item.flowable() for item in self.list_item],
                           style='bulleted')
        except AttributeError:  # empty list
            return rt.DummyFlowable()


class List_Item(DocutilsGroupingNode):
    pass


class Definition_List(DocutilsBodyNode):
    def build_flowable(self):
        return rt.DefinitionList([item.process()
                                  for item in self.definition_list_item])


class Definition_List_Item(DocutilsBodySubNode):
    def process(self):
        term = self.term.styled_text()
        try:
            term += ' : ' + self.classifier.styled_text()
        except AttributeError:
            pass
        return (rt.DefinitionTerm([rt.Paragraph(term)]),
                self.definition.flowable())


class Term(DocutilsInlineNode):
    def build_styled_text(self):
        content = self.process_content()
        ids = self.get('ids')
        if ids:
            # TODO: add destination for each id
            destination = rt.NamedDestination(ids[0])
            content = rt.AnnotatedText(content, destination)
        return content


class Classifier(DocutilsInlineNode):
    def build_styled_text(self):
        return self.process_content('classifier')


class Definition(DocutilsGroupingNode):
    grouped_flowables_class = rt.Definition


class Field_List(DocutilsBodyNode):
    def build_flowable(self):
        return rt.FieldList([field.flowable() for field in self.field])


class Field(DocutilsBodyNode):
    @property
    def name(self):
        return str(self.field_name.styled_text())

    @property
    def value(self):
        return self.field_body.flowable()

    def build_flowable(self):
        label = rt.Paragraph(self.field_name.styled_text(), style='field_name')
        return rt.LabeledFlowable(label, self.field_body.flowable())


class Field_Name(DocutilsInlineNode):
    pass


class Field_Body(DocutilsGroupingNode):
    pass


class Option_List(DocutilsBodyNode):
    def build_flowable(self):
        return rt.FieldList([item.flowable() for item in self.option_list_item])


class Option_List_Item(DocutilsBodyNode):
    def build_flowable(self):
        return rt.LabeledFlowable(self.option_group.flowable(),
                                  self.description.flowable(), style='option')


class Option_Group(DocutilsBodyNode):
    def build_flowable(self):
        options = (option.styled_text() for option in self.option)
        return rt.Paragraph(intersperse(options, ', '), style='option_group')


class Option(DocutilsInlineNode):
    def build_styled_text(self):
        text = self.option_string.styled_text()
        try:
            delimiter = rt.MixedStyledText(self.option_argument['delimiter'],
                                           style='option_string')
            text += delimiter + self.option_argument.styled_text()
        except AttributeError:
            pass
        return rt.MixedStyledText(text)


class Option_String(DocutilsInlineNode):
    def build_styled_text(self):
        return rt.MixedStyledText(self.process_content(), style='option_string')


class Option_Argument(DocutilsInlineNode):
    def build_styled_text(self):
        return rt.MixedStyledText(self.process_content(), style='option_arg')


class Description(DocutilsGroupingNode):
    pass


class Image(DocutilsBodyNode, DocutilsInlineNode):
    @property
    def image_path(self):
        return self.get('uri')

    def build_flowable(self):
        width_string = self.get('width')
        return rt.Image(self.image_path, scale=self.get('scale', 100) / 100,
                        width=convert_quantity(width_string))

    def build_styled_text(self):
        return rt.InlineImage(self.image_path)


class Figure(DocutilsGroupingNode):
    grouped_flowables_class = rt.Figure

    def build_flowable(self, **kwargs):
        return rt.Float(super().build_flowable(**kwargs))


class Caption(DocutilsBodyNode):
    def build_flowable(self):
        return rt.Caption(super().process_content())


class Legend(DocutilsGroupingNode):
    style = 'legend'


class Transition(DocutilsBodyNode):
    def build_flowable(self):
        return rt.HorizontalRule()


RE_LENGTH_PERCENT_UNITLESS = re.compile(r'^(?P<value>\d+)(?P<unit>[a-z%]*)$')

# TODO: warn on px or when no unit is supplied
DOCUTILS_UNIT_TO_DIMENSION = {'': PT,    # assume points for unitless quantities
                              'in': INCH,
                              'cm': CM,
                              'mm': MM,
                              'pt': PT,
                              'pc': PICA,
                              'px': DimensionUnit(1 / 100 * INCH),
                              '%': PERCENT,
                              'em': None,
                              'ex': None}


def convert_quantity(quantity_string):
    if quantity_string is None:
        return None
    value, unit = RE_LENGTH_PERCENT_UNITLESS.match(quantity_string).groups()
    return float(value) * DOCUTILS_UNIT_TO_DIMENSION[unit]


class Table(DocutilsBodyNode):
    def build_flowable(self):
        tgroup = self.tgroup
        if tgroup.get('colwidths', 'auto') == 'given':
            column_widths = [int(colspec.get('colwidth'))
                             for colspec in tgroup.colspec]
        else:
            column_widths = None
        try:
            head = tgroup.thead.get_table_section()
        except AttributeError:
            head = None
        body = tgroup.tbody.get_table_section()
        width_string = self.get('width')
        table = rt.Table(body, head=head, width=convert_quantity(width_string),
                         column_widths=column_widths)
        try:
            caption = rt.Caption(self.title.process_content())
            return rt.TableWithCaption([caption, table])
        except AttributeError:
            return table


class TGroup(DocutilsNode):
    pass


class ColSpec(DocutilsNode):
    pass


class TableRowGroup(DocutilsNode):
    section_cls = None

    def get_table_section(self):
        return self.section_cls([row.get_row() for row in self.row])


class THead(TableRowGroup):
    section_cls = rt.TableHead


class TBody(TableRowGroup):
    section_cls = rt.TableBody


class Row(DocutilsNode):
    def get_row(self):
        return rt.TableRow([entry.flowable() for entry in self.entry])


class Entry(DocutilsGroupingNode):
    grouped_flowables_class = rt.TableCell

    def build_flowable(self):
        rowspan = int(self.get('morerows', 0)) + 1
        colspan = int(self.get('morecols', 0)) + 1
        return super().build_flowable(rowspan=rowspan, colspan=colspan)


class Raw(DocutilsBodyNode):
    def build_flowable(self):
        if self['format'] == 'pdf':   # rst2pdf
            if self.text == 'PageBreak':
                return rt.PageBreak(style=rt.PageBreakStyle(page_break=True))
            return rt.WarnFlowable("Unsupported raw pdf option: '{}'"
                                   .format(self.text))
        return rt.DummyFlowable()


class Container(DocutilsGroupingNode):
    pass
