#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014, Thorsten Behrens
# Copyright (c) 2010, Bart Hanssens
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#

# use of lpod inspired by Bart Hanssens' odflinkchecker.py,
# https://lists.oasis-open.org/archives/opendocument-users/201008/msg00004.html
# and lpod-python-recipes
#
import sys
import mistune
import argparse
from lpod.document import odf_get_document
from lpod.frame import odf_create_text_frame
from lpod.draw_page import odf_create_draw_page, odf_draw_page
from lpod.list import odf_create_list_item, odf_create_list
from lpod.style import odf_create_style
from lpod.paragraph import odf_create_paragraph, odf_span, odf_create_line_break
from lpod.element import odf_create_element
from lpod.link import odf_create_link

def wrap_spans(odf_elements):
    '''For any homogeneous toplevel range of text:span elements, wrap them
       into a paragraph'''
    res = []
    para = None
    for elem in odf_elements:
        if isinstance(elem, odf_span):
            if para is None:
                para = odf_create_paragraph()
            para.append(elem)
        else:
            if para is not None:
                res.append(para)
                para = None
            res.append(elem)
    if para is not None:
        res.append(para)
    return res


# really quite an ugly hack. but unfortunately, mistune at a few
# non-overridable places use '+' and '+=' to concatenate render method
# returns. Due to the nature of the parser, to preserve output
# ordering, we need to return odf partial trees in our own render
# methods (that will then need to be concatenated via +/+=).
class ODFPartialTree:
    def __init__(self, elements):
        self._elements = elements

    def _add_child_elems(self, elems):
        if (len(self._elements)
              and isinstance(self._elements[-1], odf_draw_page)
              and not isinstance(elems[0], odf_draw_page)):

            elems = wrap_spans(elems)
            # stick additional frame content into last existing one
            for child in self._elements[-1].get_elements('descendant::draw:frame'):
                if child.get_presentation_class() == u'outline':
                    text_box = child.get_children()[0]
                    for elem in elems:
                        text_box.append(elem)
                    return

            # no outline frame found, create new one with elems content
            self._elements[-1].append(
                odf_create_text_frame(
                    elems,
                    presentation_style=u'pr7',
                    size = (u'22cm', u'12cm'),
                    position = (u'2cm', u'5cm'),
                    presentation_class = u'outline'))
        else:
            self._elements += elems

    def _add_text(self, text):
        span = odf_create_element('text:span')
        span.set_text(unicode(text))
        self._elements.append( span )

    def __add__(self, other):
        tmp = ODFPartialTree(list(self._elements))
        if isinstance(other, str):
            tmp._add_text(other)
        else:
            tmp._add_child_elems(other._elements)
        return tmp

    def __iadd__(self, other):
        if isinstance(other, str):
            self._add_text(other)
        else:
            self._add_child_elems(other._elements)
        return self

    def __copy__(self):
        return ODFPartialTree(self._elements[:])

    def get(self):
        return self._elements


class ODFRenderer(mistune.Renderer):
    def __init__(self, document):
        self.document = document
        self.add_style('text', u'TextEmphasisStyle',
                       [('text', {'font_style': u'italic'})])
        self.add_style('text', u'TextDoubleEmphasisStyle',
                       [('text', {'font_style': u'italic', 'font_weight': u'bold'})])
        self.add_style('text', u'TextQuoteStyle',
                       # TODO: font size increase does not work currently
                       [('text', {'size': u'150%',
                                  'color': u'#ccf4c6'})])
        self.add_style('paragraph', u'ParagraphQuoteStyle',
                       [('text', {'color': u'#18a303'}),
                        ('paragraph', {'margin_left': u'0.5cm',
                                       'margin_right': u'0.5cm',
                                       'margin_top': u'0.5cm',
                                       'margin_bottom': u'0.5cm',
                                       'text_indent': u'-0.5cm'})])
        self.add_style('text', u'TextCodeStyle',
                       # TODO: neither font, nor font size work currently
                       [('text', {'size': u'110%',
                                  'font_name': u'Courier', 'font_family': u'monospaced'})])
        self.add_style('paragraph', u'ParagraphCodeStyle',
                       # TODO: neither font, nor font size work currently
                       [('text', {'size': u'110%',
                                  'font_name': u'Courier', 'font_family': u'monospaced'}),
                        ('paragraph', {'margin_left': u'0.5cm',
                                       'margin_right': u'0.5cm',
                                       'margin_top': u'0.5cm',
                                       'margin_bottom': u'0.5cm',
                                       'text_indent': u'0cm'})])

    def add_style(self, style_family, style_name, properties):
        """Insert global style into document"""
        style = odf_create_style (
            style_family,
            name=style_name)
        for elem in properties:
            style.set_properties(properties=elem[1], area=elem[0])
        self.document.insert_style(style, automatic=True)

    def placeholder(self):
        return ODFPartialTree([])

    def block_code(self, code, language=None):
        para = odf_create_paragraph(style=u'ParagraphCodeStyle')
        for line in code.splitlines():
            span = odf_create_element('text:span')
            span.set_text(unicode(line))
            para.append(span)
            para.append(odf_create_line_break())
        return ODFPartialTree([para])

    def header(self, text, level, raw=None):
        page = None
        if level == 1:
            page = odf_create_draw_page(
                'page1',
                name=''.join(e.get_formatted_text() for e in text.get()),
                master_page=u'Break',
                presentation_page_layout=u'AL3T19')
            page.append(
                odf_create_text_frame(
                    wrap_spans(text.get()),
                    presentation_style=u'pr9',
                    size = (u'20cm', u'3cm'),
                    position = (u'2cm', u'8cm'),
                    presentation_class = u'title'))
        elif level == 2:
            page = odf_create_draw_page(
                'page1',
                name=''.join(e.get_formatted_text() for e in text.get()),
                master_page=u'Logo_20_Content',
                presentation_page_layout=u'AL3T1')
            page.append(
                odf_create_text_frame(
                    wrap_spans(text.get()),
                    presentation_style=u'pr6',
                    size = (u'20cm', u'3cm'),
                    position = (u'2cm', u'1cm'),
                    presentation_class = u'title'))
        else:
            raise RuntimeError('Unsupported heading level: %d' % level)

        return ODFPartialTree([page])

    def block_quote(self, text):
        para = odf_create_paragraph(style=u'ParagraphQuoteStyle')
        span = odf_create_element('text:span')
        span.set_text(u'“')
        para.append(span)

        span = odf_create_element('text:span')
        for elem in text.get():
            span.append(elem)
        para.append(span)

        span = odf_create_element('text:span')
        span.set_text(u'”')
        para.append(span)

        para.set_span(u'TextQuoteStyle', regex=u'“')
        para.set_span(u'TextQuoteStyle', regex=u'”')
        return ODFPartialTree([para])

    def list_item(self, text):
        item = odf_create_list_item()
        for elem in wrap_spans(text.get()):
            item.append(elem)
        return ODFPartialTree([item])

    def list(self, body, ordered=True):
        lst = odf_create_list(style=u'L6' if ordered else u'L2')
        for elem in body.get():
            lst.append(elem)
        return ODFPartialTree([lst])

    def paragraph(self, text):
        # yes, this seem broadly illogical. but most 'paragraphs'
        # actually end up being parts of tables, quotes, list items
        # etc, which might not always permit text:p
        span = odf_create_element('text:span')
        for elem in text.get():
            span.append(elem)
        return ODFPartialTree([span])

    def table(self, header, body):
        pass

    def table_row(self, content):
        pass

    def table_cell(self, content, **flags):
        pass

    def autolink(self, link, is_email=False):
        text = link
        if is_email:
            link = 'mailto:%s' % link
        lnk = odf_create_link(link, text=unicode(text))
        return ODFPartialTree([lnk])

    def link(self, link, title, content):
        lnk = odf_create_link(link, text=unicode(content), title=unicode(title))
        return ODFPartialTree([lnk])

    def codespan(self, text):
        span = odf_create_element('text:span')
        span.set_style('TextCodeStyle')
        if isinstance(text, str):
            span.set_text(unicode(text))
        else:
            for elem in text.get():
                span.append(elem)
        return ODFPartialTree([span])

    def double_emphasis(self, text):
        span = odf_create_element('text:span')
        span.set_style('TextDoubleEmphasisStyle')
        for elem in text.get():
            span.append(elem)
        return ODFPartialTree([span])

    def emphasis(self, text):
        span = odf_create_element('text:span')
        span.set_style('TextEmphasisStyle')
        for elem in text.get():
            span.append(elem)
        return ODFPartialTree([span])

    def image(self, src, title, alt_text):
        pass

    def linebreak(self):
        return ODFPartialTree([odf_create_line_break()])

    def tag(self, html):
        pass

    def strikethrough(self, text):
        pass

# main script
parser = argparse.ArgumentParser(description='Convert markdown text into OpenDocument presentations')
parser.add_argument('input_md',
                    type=argparse.FileType('r'),
                    help='Input markdown file')
parser.add_argument('template_odp',
                    type=argparse.FileType('r'),
                    help='Input ODP template file')
parser.add_argument('output_odp',
                    type=argparse.FileType('w'),
                    help='Output ODP file')
parser.add_argument('-p', '--page', default=-1, type=int,
                    help='Append markdown after given page. Negative numbers count from the'
                         ' end of the slide stack')
args = parser.parse_args()

markdown = args.input_md
odf_in = args.template_odp
odf_out = args.output_odp
presentation = odf_get_document(odf_in)

odf_renderer = ODFRenderer(presentation)
mkdown = mistune.Markdown(renderer=odf_renderer)

doc_elems = presentation.get_body()
if args.page < 0:
    args.page = len(doc_elems.get_children()) + args.page

for index, page in enumerate(mkdown.render(markdown.read()).get()):
    doc_elems.insert(page, position=args.page + index)

presentation.save(target=odf_out, pretty=True)
