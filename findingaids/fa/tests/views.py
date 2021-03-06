# file findingaids/fa/tests/views.py
#
#   Copyright 2012 Emory University Library
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from os import path
from types import ListType
from lxml import etree
from mock import patch
import unittest
from urllib import quote as urlquote

from django.conf import settings
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.test.utils import override_settings

from eulexistdb.db import ExistDB, ExistDBException
from eulexistdb.testutil import TestCase
from eulxml.xmlmap import load_xmlobject_from_file, \
    load_xmlobject_from_string

from findingaids.fa.models import FindingAid, Series, Series2, Series3, \
    Deleted
from findingaids.fa.views import _series_url, _subseries_links, _series_anchor

## unit tests for views and template logic

exist_fixture_path = path.join(path.dirname(path.abspath(__file__)), 'fixtures')
exist_index_path = path.join(path.dirname(path.abspath(__file__)), '..', '..', 'exist_index.xconf')


class FaViewsTest(TestCase):
    fixtures = ['user']
    exist_fixtures = {'directory': exist_fixture_path}
    # NOTE: views that require full-text search tested separately below for response-time reasons
    exist_files = []    # place-holder for any fixtures loaded by individual tests

    def setUp(self):
        self.db = ExistDB()

    def tearDown(self):
        # clean up any documents that were created by individual tests
        for f in self.exist_files:
            try:
                self.db.removeDocument(f)
            except ExistDBException:
                pass
        self.exist_files = []

    def test_title_letter_list(self):
        # clear out any cached title letters from previous tests
        cache.set('browse-title-letters', None)

        titles_url = reverse('fa:browse-titles')
        response = self.client.get(titles_url)
        expected = 200
        self.assertEqual(response.status_code, expected, 'Expected %s but returned %s for %s'
                         % (expected, response.status_code, titles_url))

        # first letters from 4 test documents
        for letter in ['A', 'B', 'L', 'R']:
            self.assertContains(
                response,
                'href="%s"' % reverse('fa:titles-by-letter', kwargs={'letter': letter}),
                msg_prefix="browse titles should link to titles starting with %s    " % letter)

        # should not include first letters not present in the data
        self.assertContains(
            response,
            'href="%s"' % reverse('fa:titles-by-letter', kwargs={'letter': 'Z'}),
            0, msg_prefix='browse titles should not link to titles starting with Z')

    def test_titles_by_letter(self):
        # load a modified copy of abbey244 to test case-insensitive sorting (for this test only)
        alphatest_dbpath = settings.EXISTDB_ROOT_COLLECTION + '/alpha-test.xml'
        ead = load_xmlobject_from_file(path.join(exist_fixture_path, 'abbey244.xml'), FindingAid)
        ead.list_title.node.text = 'ABC alpha-test'
        self.db.load(ead.serialize(), alphatest_dbpath, overwrite=True)
        self.exist_files.append(alphatest_dbpath)

        a_titles = reverse('fa:titles-by-letter', kwargs={'letter': 'A'})
        response = self.client.get(a_titles)
        session = self.client.session
        expected = 200
        last_search = session.get("last_search", None)  # browse query info stored in the session
        self.assertTrue(last_search)
        self.assertEqual(
            "%s?page=1" % (reverse('fa:titles-by-letter', kwargs={'letter': 'A'})),
            last_search['url'], "session url should match title-by-letter with page number")

        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s'
                         % (expected, response.status_code, a_titles))
        self.assertContains(
            response,
            'href="%s' % reverse('fa:findingaid', kwargs={'id': 'abbey244'}),
            msg_prefix='browse by titles for A should link to Abbey finding aid')
        self.assertContains(
            response, '<p class="abstract">Collection of play scripts',
            msg_prefix='browse by titles for A should include Abbey finding aid abstract')
        self.assertContains(
            response, '3 finding aids found',
            msg_prefix='browse by titles for A should return 3 finding aids')
        self.assertPattern(
            r'4 linear ft..*; .*(8 boxes)', response.content,
            msg_prefix='browse view should handle multiple physdesc elements')

        # test case-insensitive sorting
        self.assertPattern(
            'Abbey.*ABC', response.content,
            msg_prefix='Abbey Theater should be listed before ABC (case-insensitive sort)')
        # test pagination
        self.assertContains(
            response, 'Ab - Ad',
            msg_prefix='browse pagination uses first letters of titles instead of numbers')

        # test current letter
        self.assertContains(
            response,
            "<a class='current' href='%s'>A</a>" % reverse('fa:titles-by-letter',
                                                           kwargs={'letter': 'A'}),
            html=True,
            msg_prefix='browse by letter A should mark A as current letter')

        # format_ead
        # NOTE: these tests are somewhat dependent on whitespace in the xml fixtures
        response = self.client.get(reverse('fa:titles-by-letter',
                                   kwargs={'letter': 'P'}))
        # title
        self.assertContains(
            response, '''<p><span class="ead-title">Where Peachtree Meets Sweet Auburn</span>
            research files and interviews, 1991-1996</p>''',
            msg_prefix='title with formatting should be formatted in list view',
            html=True)
        # abstract
        self.assertPattern(r'''book,\s+<[-A-Za-z="' ]+>Where Peachtree Meets Sweet Auburn:''',
                           response.content,
                           msg_prefix='abstract with formatting should be formatted in list view')
        # repository subarea
        self.assertPattern(r'''Repository: Manuscript,\s+Archives,\s+and\s+Rare\s+Book\s+Library/Pitts Theology Library''',
                           response.content,
                           msg_prefix='short-record view should include multiple holding repositories')

        # no finding aids
        response = self.client.get(reverse('fa:titles-by-letter',
                                   kwargs={'letter': 'Z'}))
        self.assertPattern('<div>No finding aids found for .*Z.*</div>',
                           response.content,
                           msg_prefix="titles by letter 'Z' should return no finding aids")

        response = self.client.get(reverse('fa:titles-by-letter',
                                   kwargs={'letter': 'B'}))

        # finding aid with no origination - unit title used as browse title & link
        # - unit title should only be displayed once
        self.assertContains(
            response, 'Bailey and Thurman families papers', 1,
            msg_prefix="finding aid with no origination should use unit title once as title & link")

        # Additional case for doubled title problem -title with formatting
        response = self.client.get(reverse('fa:titles-by-letter',
                                   kwargs={'letter': 'P'}))
        self.assertContains(response, 'Pitts v. Freeman', 2)  # Title and abstract
        #title within unittitle
        self.assertPattern(
            r'''Pitts v. Freeman</[-A-Za-z]+> school''', response.content,
            msg_prefix='title within unittitle should be formatted on list view')

    def test_titles_xml(self):
        xml_titles = reverse('fa:all-xml')
        response = self.client.get(xml_titles)
        expected = 200
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s'
                         % (expected, response.status_code, xml_titles))
        # all eads from test fixtures should be listed
        for eadid in ['abbey244', 'bailey807', 'leverette135', 'adams465',
                      'pittsfreeman1036.xml', 'pomerantz890', 'raoul548']:
            self.assertContains(
                response, '%s.xml' % eadid,
                msg_prefix='eadid %s should be included in all-xml page' % eadid)
            self.assertContains(response, reverse('fa:eadxml', kwargs={'id': eadid}))

# view finding aid main page

    def test_view_notfound(self):
        nonexistent_ead = reverse('fa:findingaid', kwargs={'id': 'nonexistent'})
        response = self.client.get(nonexistent_ead)
        expected = 404
        self.assertEqual(
            response.status_code, expected,
            'Expected %s but returned %s for nonexistent EAD at %s'
            % (expected, response.status_code, nonexistent_ead))

    def test_deleted(self):
        # 410 gone - not found in exist, but there is a record indicating it was deleted
        # create a Deleted record for testing
        id, title, note = 'deleted', 'Deleted EAD record', 'removed because of foo'
        Deleted(eadid=id, title=title, note=note).save()

        # test a deleted record in all 3 single-finding aid top-level views
        # view_fa (main html view)
        fa_url = reverse('fa:findingaid', kwargs={'id': id})
        response = self.client.get(fa_url)
        expected, got = 410, response.status_code
        self.assertEqual(
            expected, got,
            'Expected %s but returned %s for deleted EAD at %s' %
            (expected, response.status_code, fa_url))
        self.assertContains(
            response, '<h1>%s</h1>' % title, status_code=410,
            msg_prefix="title from deleted record is displayed in response")
        self.assertContains(
            response, note, status_code=410,
            msg_prefix="note from deleted record are displayed in response")

        # full_fa (single-page html version of entire Finding Aid, basis for PDF)
        full_url = reverse('fa:full-findingaid', kwargs={'id': id})
        response = self.client.get(full_url)
        expected, got = 410, response.status_code
        self.assertEqual(
            expected, got,
            'Expected %s but returned %s for deleted EAD at %s' %
            (expected, response.status_code, full_url))
        self.assertContains(
            response, '<h1>%s</h1>' % title, status_code=410,
            msg_prefix="title from deleted record is displayed in response")

        # printable_fa - PDF of entire Finding Aid
        pdf_url = reverse('fa:printable', kwargs={'id': id})
        response = self.client.get(pdf_url)
        expected, got = 410, response.status_code
        self.assertEqual(
            expected, got,
            'Expected %s but returned %s for deleted EAD at %s' %
            (expected, response.status_code, pdf_url))
        self.assertContains(
            response, '<h1>%s</h1>' % title, status_code=410,
            msg_prefix="title from deleted record is displayed in response")

        # xml_fa - full XML EAD content for a single finding aid
        xml_url = reverse('fa:eadxml', kwargs={'id': id})
        response = self.client.get(xml_url)
        expected, got = 410, response.status_code
        self.assertEqual(
            expected, got,
            'Expected %s but returned %s for deleted EAD at %s' %
            (expected, response.status_code, full_url))
        self.assertContains(
            response, '<h1>%s</h1>' % title, status_code=410,
            msg_prefix="title from deleted record is displayed in response")

    def test_view_dc_fields(self):
        response = self.client.get(reverse('fa:findingaid', kwargs={'id': 'abbey244'}))
        # TODO: would be nice to validate the DC output...  (if possible)

        #DC.creator
        self.assertContains(response, '<meta name="DC.creator" content="Abbey Theatre." />')
        #DC.publisher
        self.assertContains(response, '<meta name="DC.publisher" content="Emory University" />')
        #date
        self.assertContains(response, '<meta name="DC.date" content="2002-02-24" />')
        #language
        self.assertContains(response, '<meta name="DC.language" content="eng" />')
        #dc_subjects
        self.assertContains(response, '<meta name="DC.subject" content="Irish drama--20th century." />')
        self.assertContains(response, '<meta name="DC.subject" content="Theater--Ireland--20th century." />')
        self.assertContains(response, '<meta name="DC.subject" content="Dublin (Ireland)" />')
        #DC.identifer
        self.assertContains(response, '<meta name="DC.identifier" content="http://pidtest.library.emory.edu/ark:/25593/1fx" />')

        # Permalink with bookmark rel and ARK
        self.assertContains(response,
                            '<a property="schema:url" rel="bookmark" href="http://pidtest.library.emory.edu/ark:/25593/1fx">http://pidtest.library.emory.edu/ark:/25593/1fx</a>',
                            html=True)

        #link in header with bookmark rel and ARK
        self.assertContains(response, '<link rel="bookmark" href="http://pidtest.library.emory.edu/ark:/25593/1fx" />')

        response = self.client.get(reverse('fa:findingaid', kwargs={'id': 'bailey807'}))
        #title
        self.assertContains(response, '<meta name="DC.title" content="Bailey and Thurman families papers, circa 1882-1995" />')
        #dc_contributors
        self.assertContains(response, '<meta name="DC.contributor" content="Bailey, I. G. (Issac George), 1847-1914." />')
        self.assertContains(response, '<meta name="DC.contributor" content="Bailey, Susie E., d. 1948." />')
        self.assertContains(response, '<meta name="DC.contributor" content="Thurman, Howard, 1900-1981." />')
        self.assertContains(response, '<meta name="DC.contributor" content="Thurman, Sue Bailey." />')

    def test_view_simple(self):
        fa_url = reverse('fa:findingaid', kwargs={'id': 'leverette135'})
        response = self.client.get(fa_url)
        expected = 200
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s' %
                         (expected, response.status_code, fa_url))

        # title
        self.assertPattern('<h1[^>]*>.*Fannie Lee Leverette scrapbooks', response.content)
        self.assertNotContains(
            response, 'circa 1900-1948</h1>',
            msg_prefix='finding aid title should be unittitle without unitdate')

        # descriptive summary content
        self.assertPattern('Creator:.*Leverette, Fannie Lee', response.content,
                           "descriptive summary - creator")
        self.assertPattern('Title:.*Fannie Lee Leverette scrapbooks,circa 1900-1948',
                           response.content, "descriptive summary - title")
        self.assertPattern('Call Number:.*Manuscript Collection.+No.135', response.content,
                           "descriptive summary - call number")
        self.assertPattern('Extent:.*1 microfilm reel.+MF', response.content,
                           "descriptive summary - extent")
        self.assertPattern('Abstract:.*Microfilm copy of four scrapbooks', response.content,
                           "descriptive summary - abstract")
        self.assertPattern('Language:.*Materials entirely in.+English', response.content,
                           "descriptive summary - language")
        self.assertNotContains(response, 'Location:')       # not in xml, should not display

        # admin info
        self.assertPattern('Restrictions on Access.*Unrestricted access.', response.content,
                           "admin info - access restrictions")
        self.assertPattern('Terms Governing Use and Reproduction.*All requests subject to limitations.',
                           response.content, "admin info - use restrictions")
        self.assertPattern('Source.*Loaned for reproduction, 1978.', response.content,
                           "admin info - source")
        self.assertPattern('Citation.*\[after identification of item\(s\)\], Fannie Lee Leverette scrapbooks.',
                           response.content, "admin info - preferred citation")
        self.assertNotContains(response, 'Related Materials')       # not in xml, should not display

        # collection description
        self.assertPattern('Biographical Note.*born in Eatonton, Putnam County, Georgia',
                           response.content, "collection description - biography")
        self.assertPattern('Scope and Content Note.*collection consists of',
                           response.content, "collection description - scope & content")

        # controlaccess
        self.assertPattern('<h2>.*Selected Search Terms.*</h2>', response.content,
                           "control access heading")
        self.assertPattern('<h3>Personal Names</h3>.*Collins, M\.D\..*Farley, James A\.',
                           response.content, "control access - personal names")
        self.assertPattern('<h3>Topical Terms</h3>.*African Americans--Georgia--Eatonton\..*Education--Georgia\.|',
                           response.content, "control access - subjects")
        self.assertPattern('<h3>Geographic Names</h3>.*Augusta \(Ga\.\).*Eatonton \(Ga\.\)',
                           response.content, "control access - geography")
        self.assertPattern('<h3>Form/Genre Terms</h3>.*Photographs\..*Scrapbooks\.',
                           response.content, "control access - form/genre")
        self.assertPattern('<h3>Occupation</h3>.*Educator\..*Journalist',
                           response.content, "control access - occupation")

        # controlaccess terms link to subject search
        search_url = reverse('fa:search')
        self.assertContains(
            response,
            '''href='%s?subject="%s"''' % (search_url, urlquote('Collins, M.D.')),
            msg_prefix='controlaccess person name links to subject search')
        self.assertContains(
            response,
            '''href='%s?subject="%s"''' % (search_url,
                                           urlquote('African Americans--Georgia--Eatonton.')),
            msg_prefix='controlaccess subject links to subject search')
        self.assertContains(
            response,
            '''href='%s?subject="%s"''' % (search_url, urlquote('Augusta (Ga.).')),
            msg_prefix='controlaccess geogname links to subject search')
        self.assertContains(
            response,
            '''href='%s?subject="%s"''' % (search_url, urlquote('Scrapbooks.')),
            msg_prefix='controlaccess genreform links to subject search')
        self.assertContains(
            response,
            '''href='%s?subject="%s"''' % (search_url, urlquote('Journalist.')),
            msg_prefix='controlaccess occupation links to subject search')

        # dsc
        self.assertPattern(
            '<h2>.*Container List.*</h2>', response.content,
            "simple finding aid (leverette) view includes container list")
        self.assertPattern(
            'Scrapbook 1.*Box.*Folder.*Content.*MF1', response.content,
            "Scrapbook 1 in container list")    # box/folder now after section label if any
        self.assertPattern(
            'MF1.*1.*Photo and clippings re Fannie Lee Leverette',
            response.content, "photo clippings in container list")
        self.assertPattern(
            'MF1.*4.*Family and personal photos|', response.content,
            "family photos in container list")
        # container list included in top-level contents
        self.assertPattern(
            '<li>.*Container List.*</li>', response.content,
            'container list included in top-level table of contents')


        # title with formatting
        response = self.client.get(reverse('fa:findingaid', kwargs={'id': 'pomerantz890'}))
        self.assertPattern(r'''Sweet Auburn</[-A-Za-z]+>\s*research files''',
                           response.content)  # title
        # Title appears twice, we need to check both locations, 'EAD title' and 'Descriptive Summary'
        self.assertPattern(r'''<h1[^>]*>.*\s+<[-A-Za-z="' ]+>Where Peachtree Meets Sweet Auburn''',
                           response.content)  # EAD title
        self.assertPattern(r'''<table id="descriptive_summary">.*\s+<[-A-Za-z="' ]+>Where Peachtree Meets Sweet Auburn''',
                           response.content)  # Descriptive Summary title

        self.assertPattern(r'''book,\s+<[-A-Za-z="' ]+>Where Peachtree Meets Sweet Auburn:''',
                           response.content)  # abstract
        self.assertPattern(r'''\[after identification of item\(s\)\],\s+<[-A-Za-z="' ]+>Where Peachtree''',
                           response.content)  # admin_info
        # Note: titles now include RDFa in bioghist, so multiple tags here
        self.assertPattern(r'''joined\s+(<[-A-Za-z=:"' ]+>)*The Washington Post''',
                           response.content)  # collection description

        # only descriptive information that is present
        response = self.client.get(reverse('fa:findingaid', kwargs={'id': 'bailey807'}))
        self.assertNotContains(response, 'Creator:')

        # header link to EAD xml
        response = self.client.get(reverse('fa:findingaid', kwargs={'id': 'pomerantz890'}))
        self.assertContains(response, 'href="%s"' % reverse('fa:eadxml', kwargs={'id': 'pomerantz890'}))

        self.assertNotContains(
            response, '<meta name="robots" content="noindex,nofollow"',
            msg_prefix="non-highlighted finding aid does NOT include robots directives noindex, nofollow")

    def test_view_dao(self):
        fa_url = reverse('fa:findingaid', kwargs={'id': 'leverette135'})
        response = self.client.get(fa_url)

        # dao with audience=external converted to html links
        self.assertContains(
            response, '<a class="dao" href="http://some.url/item/id2">Photo 1</a>',
            html=True,
            msg_prefix='dao should be converted to html link using href & attribute')
        self.assertContains(
            response, '<a class="dao" href="http://some.url/item/id3">Photo 2</a>',
            html=True,
            msg_prefix='multiple daos in the same did should be converted')
        # external with show=none should be suppressed
        self.assertNotContains(response, 'http://some.url/item/id7',
            msg_prefix='external dao with show=none should not be displayed')
        # external with no href; fallback to reading room display
        self.assertContains(response,
            '<a class="dao">[Reading Room access only: id dm4567]</a>',
            html=True,
            msg_prefix='external dao with no href should be displayed as reading room access only')

        # dao with audience=internal displayed as reading room access only with id
        self.assertContains(response,
            '<a class="dao">[Reading Room access only: id dm1234]</a>',
            html=True,
            msg_prefix='internal dao should be displayed as reading room access only')

        def_link_text = getattr(settings, 'DEFAULT_DAO_LINK_TEXT',
                                '[Resource available online]')
        self.assertContains(
            response,
            '<a class="dao" href="http://some.url/item/id4">%s</a>' % def_link_text,
            html=True,
            msg_prefix='dao with no title should use configured default')

        self.assertNotContains(
            response,
            '<a class="dao dao-internal" href="http://some.url/item/id1">Digitized Content</a>',
            html=True,
            msg_prefix='dao with audience=internal should not display to anonymous user')
        # show=none
        self.assertNotContains(
            response,
            '<a class="dao dao-internal dao-hidden" href="http://some.url/item/id5">Hide Me</a>',
            html=True,
            msg_prefix='dao with audience=internal and show=none should not display to anonymous user')

        # when logged in as an admin, internal dao *should* be displayed
        self.client.login(username='marbl', password='marbl')
        response = self.client.get(fa_url)
        self.assertContains(
            response,
            '<a class="dao dao-internal" href="http://some.url/item/id1">Digitized Content</a>',
            html=True,
            msg_prefix='dao with audience=internal should display for admin user')

        # dao with audience=internal and NO href displayed as reading room access only with id
        self.assertContains(response,
           '[Reading Room access only: id dm1234]',
            msg_prefix='internal dao without href should display as reading room access only to admins')
        # internal show=none
        self.assertContains(
            response,
            '<a class="dao dao-internal dao-hidden" href="http://some.url/item/id5">Hide Me</a>',
            html=True,
            msg_prefix='dao with audience=internal and show=none should display to admin user')
        # external show=none
        self.assertContains(response,
            '<a class="dao dao-hidden" href="http://some.url/item/id7">%s</a>' % def_link_text,
            html=True,
            msg_prefix='external dao with show=none should be displayed to admin user')


    def test_view__fa_with_series(self):
        fa_url = reverse('fa:findingaid', kwargs={'id': 'abbey244'})
        response = self.client.get(fa_url)
        expected = 200
        self.assertEqual(
            response.status_code, expected,
            'Expected %s but returned %s for %s' % (expected,
            response.status_code, fa_url))

        # admin info fields not present in leverette
        self.assertPattern(
            'Related Materials in This Repository.*William Butler Yeats collection',
            response.content, "admin info - related materials")
        self.assertPattern(
            'Historical Note.*Abbey Theatre, organized in 1904',
            response.content, "admin info - historical note")
        self.assertPattern(
            'Arrangement Note.*Organized into three series',
            response.content, "admin info - arrangement")
        self.assertPattern(
            r'4 linear ft..*; .*(8 boxes)', response.content,
            msg_prefix='findingaid view should handle multiple physdesc elements')
      #   self.assertContains(response, '<head>Processing</head>'
      # '<p>Processed by Susan Potts McDonald, 2000.</p>', html=true)

        # series instead of container list
        self.assertPattern(
            '<h2>.*Description of Series.*</h2>', response.content,
            "finding aid with series includes description of series")
        self.assertPattern(
            '<a href.*>Series 1: Plays</a>', response.content,
            "series 1 link")
        self.assertPattern(
            '<a href.*>Series 2: Programs.*</a>', response.content,
            "series 2 link")
        self.assertPattern(
            '|<a href.*>Series 3: Other material, 1935-1941.*</a>',
            response.content, "series 3 link")
        # dsc head when series: series ToC at top, full series ToC at bottom, but not top-level ToC
        self.assertContains(
            response, 'Description of Series', 2,
            msg_prefix="'Description of Series' should only occur twice on main finding aid page")

        # link to single-finding aid feedback form
        self.assertTrue(
            response.context['feedback_opts'],
            'single finding aid feedback options should be set in response context')
        self.assertContains(
            response, reverse('content:feedback'),
            msg_prefix='url to feedback form should be included in response')

    def test_view__fa_with_subseries(self):
        fa_url = reverse('fa:findingaid', kwargs={'id': 'raoul548'})
        response = self.client.get(fa_url)
        expected = 200
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s' %
                         (expected, response.status_code, fa_url))

        # admin info fields not present in previous fixtures
        self.assertPattern(
            'Related Materials in Other Repositories.*original Wadley diaries',
            response.content, "admin info - related materials")

        # collection description - multiple paragraphs
        self.assertPattern(
            'Biographical Note.*centered in Georgia.*eleven children.*moved to New York',
            response.content, "collection description - bio with multiple paragraphs")
            # text from first 3 paragraphs
        self.assertPattern(
            'Scope and Content Note.*contain letters, journals.*arranged in four series.*document the life',
            response.content, "collection description - scote & content with multiple paragraphs")

        # series instead of container list
        self.assertPattern('<h2>.*Description of Series.*</h2>', response.content,
                           "series instead of container list")
        self.assertPattern('<a href.*>Series 1: Letters and personal papers.*</a>',
                           response.content, "series 1 link")
        self.assertPattern('<a href.*>Subseries 1\.1: William Greene Raoul paper.*</a>',
                           response.content, "subseries 1.1 link")
        self.assertPattern('<a href.*>Subseries 1\.2: Mary Wadley Raoul papers.*</a>',
                           response.content, "subseries 1.2 link")
        self.assertPattern('<a href.*>Subseries 1\.13: .*Norman Raoul papers.*</a>',
                           response.content, "subseries 1.13 link")
        self.assertPattern('<a href.*>Series 2:.*Photographs,.*circa.*1850-1960.*</a>',
                           response.content, "series 2 link")
        self.assertPattern('<a href.*>Series 4:.*Miscellaneous,.*1881-1982.*</a>',
                           response.content, "series 4 link")

    def test_view_indexentry(self):
        # main page should link to indexes in ead contents
        response = self.client.get(reverse('fa:findingaid', kwargs={'id': 'raoul548'}))
        self.assertContains(
            response, 'Index of Selected Correspondents',
            msg_prefix='main finding aid page should list Index title')
        # index links should be full urls, not same-page anchors
        index_url = reverse('fa:series-or-index', kwargs={'id': 'raoul548', 'series_id': 'index1'})
        self.assertContains(
            response, 'href="%s"' % index_url,
            msg_prefix='main finding aid page should link to index page')
        # second index
        self.assertContains(
            response, 'Second Index',
            msg_prefix='main finding aid page should list second Index title')
        index2_url = reverse('fa:series-or-index', kwargs={'id': 'raoul548', 'series_id': 'index2'})
        self.assertContains(
            response, 'href="%s"' % index2_url,
            msg_prefix='main finding aid page should link to second index page')

        # first index - on a separate page

        response = self.client.get(index_url)
        # ead title, table of contents
        self.assertContains(
            response, 'Raoul family papers',
            msg_prefix="finding aid index page includes main finding aid title")
        self.assertContains(
            response, 'Series 1',
            msg_prefix='finding aid index page includes series listing')
        self.assertContains(
            response, 'Index of Selected Correspondents',
            msg_prefix='finding aid index page includes current index title')
        # current index on TOC should not be a link
        self.assertContains(
            response, 'href="%s"' % index_url, 0,
            msg_prefix='current index is not a link in finding aid ToC')
        # should link to other index
        self.assertContains(
            response, 'href="%s"' % index2_url,
            msg_prefix='index page includes link to second index in finding aid ToC')
        # first index name and ref
        self.assertContains(
            response, 'Alexander, Edwin Porter, 1835-1910',
            msg_prefix='first index name is listed on index page')
        self.assertContains(
            response, 'Series 1 - 2:1 (2); 2:5 (1)',
            msg_prefix='first index reference is listed on index page')
        # last index name and ref
        self.assertContains(
            response, 'Woolford, T. Guy',
            msg_prefix='last index name is listed on index page')
        self.assertContains(
            response, 'Series 1 - 32:4 (10); 32:5 (3)',
            msg_prefix='reference from last index name is listed on index page')

        # second index also retrieves
        response = self.client.get(index2_url)
        self.assertContains(response, 'Second Index')

        # link to single-finding aid feedback form
        self.assertTrue(
            response.context['feedback_opts'],
            'single finding aid feedback options should be set in response context')
        self.assertContains(
            response, reverse('content:feedback'),
            msg_prefix='url to feedback form should be included in response')

    def test_view_nodsc(self):
        fa_url = reverse('fa:findingaid', kwargs={'id': 'adams465'})
        response = self.client.get(fa_url)
        expected = 200
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s' %
                         (expected, response.status_code, fa_url))

        # record with no dsc - no container list or series
        self.assertNotContains(
            response, 'Container List',
            msg_prefix='finding aid with no dsc does not include a container list')
        self.assertNotContains(
            response, 'Description of Series',
            msg_prefix='finding aid with no dsc does not include a description of series')

        # FIXME: test also not listed in top-level table of contents?


    @override_settings(REQUEST_MATERIALS_URL='http://example.com',
        REQUEST_MATERIALS_REPOS = ['Manuscript, Archives, and Rare Book Library'])
    def test_view_series__bailey_series1(self):
        # view single series in a finding aid
        series_url = reverse('fa:series-or-index', kwargs={'id': 'bailey807',
                             'series_id': 'series1'})
        response = self.client.get(series_url)
        expected = 200
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s' %
                         (expected, response.status_code, series_url))

        fa_url = reverse('fa:findingaid', kwargs={'id': 'bailey807'})
        # single series page
        # - series title
        self.assertPattern(
            '<h2>.*Series 1.*Correspondence,.*1855-1995.*</h2>',
            response.content, "series title displayed")
        # - ead title
        self.assertPattern(
            '<h1[^>]*>.*<a href="%s" rel=\"contents\">\s*Bailey and Thurman.+families papers' % fa_url,
            response.content, "finding aid title displayed, links to main record page")
        # ead toc
        self.assertPattern(
            '<a href="%s#descriptive_summary">Descriptive Summary</a>' % fa_url,
            response.content, "link to main finding aid descriptive summary")
        self.assertPattern(
            '<a href="%s#administrative_information">Administrative Information</a>' % fa_url,
            response.content, "link to main finding aid admin info")
        self.assertPattern(
            '<a href="%s#collection_description">Collection Description</a>' % fa_url,
            response.content, "link to main finding aid collection description")
        self.assertPattern(
            '<a href="%s#control_access">Selected Search Terms</a>' % fa_url,
            response.content, "link to main finding aid control access")
        # series nav
        self.assertPattern(
            '<li>[^<]*Series 1:.*Correspondence.*</li>',
            response.content, "series nav - current series not a link")
        self.assertPattern(
            '<li>.*<a href="%s".*rel="next">.*Series 2:.*Writings by Bailey family.*</a>.*</li>' %
            reverse('fa:series-or-index', kwargs={'id': 'bailey807', 'series_id': 'series2'}),
            response.content, "series nav - link to series 2")
        self.assertPattern(
            '<li>.*<a href="%s".*>.*Series 9:.*Audiovisual material.*</a>.*</li>' %
            reverse('fa:series-or-index', kwargs={'id': 'bailey807', 'series_id': 'series9'}),
            response.content, "series nav - link to series 9")
        # dsc label when series: series ToC but not top-level ToC
        self.assertContains(
            response, 'Description of Series', 1,
            msg_prefix="'Description of Series' should only occur once on main finding aid page")

        # series contents
        self.assertPattern('1.*1.*I\. G\. Bailey, 1882-1901', response.content,
                           "first content of series 1")
        self.assertPattern('2.*8.*Susie E\. Bailey, undated', response.content,
                           "sample middle content of series 1")
        self.assertPattern('3.*13.*Miscellaneous correspondence, undated', response.content,
                           "last content of series 1")

        self.assertNotContains(
            response, '<meta name="robots" content="noindex,nofollow"',
            msg_prefix="non-highlighted series does NOT include robots directives noindex, nofollow")

        # link to single-finding aid feedback form
        self.assertTrue(
            response.context['feedback_opts'],
            'single finding aid feedback options should be set in response context')
        self.assertContains(
            response, reverse('content:feedback'),
            msg_prefix='url to feedback form should be included in response')

        # series breadcrumb for ead with tag in unittitle
        series_url = reverse('fa:series-or-index', kwargs={'id': 'pomerantz890',
                             'series_id': 'series1'})
        response = self.client.get(series_url)
        expected = 200
        self.assertEqual(
            response.status_code, expected,
            'Expected %s but returned %s for %s' % (expected, response.status_code, series_url))
        self.assertPattern(
            '<span class="ead-title">Where Peachtree Meets Sweet Auburn</span> research files and interviews\s+<',
            response.content, msg_prefix='short document title in series breadcrumb should include formatted title text')
        self.assertPattern(
            '<div class="fa-title">.* >\s+Interview transcripts\s+</div>', response.content,
            msg_prefix='short series title in breadcrumb displays text without date')

        # ead should be requestable from series
        # (testing that response includes enough data for requestable method)
        self.assertTrue(response.context['ead'].requestable(),
            'Finding aid should be requestable from series page')

    def test_view_subseries__raoul_series1_6(self):
        subseries_url = reverse('fa:series2', kwargs={'id': 'raoul548',
                                'series_id': 's1', 'series2_id': 's1.6'})
        response = self.client.get(subseries_url)
        expected = 200
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s' %
                         (expected, response.status_code, subseries_url))

        # single series page
        # - series title
        self.assertPattern(
            '<h2>.*Subseries 1\.6.*Gaston C\. Raoul papers,.*1882-1959.*</h2>',
            response.content, "subseries title displayed")
        # - ead title
        self.assertPattern(
            '<h1[^>]*>.*<a href="%s" rel="contents">\s*RAOUL FAMILY.*Raoul family papers' %
            reverse('fa:findingaid', kwargs={'id': 'raoul548'}),
            response.content, "finding aid title displayed, links to main record page")

        # series nav
        self.assertPattern(
            '<li>.*<a href="%s".*rel="start">.*Series 1:.*Letters and personal papers,.*1865-1982.*</a>.*</li>' %
            reverse('fa:series-or-index', kwargs={'id': 'raoul548', 'series_id': 's1'}),
            response.content, "series nav - series 1 link")
        self.assertPattern(
            '<li>.*<a href="%s".*rel="next">.*Series 2:.*Photographs.*</a>.*</li>' %
            reverse('fa:series-or-index', kwargs={'id': 'raoul548', 'series_id': 's2'}),
            response.content, "series nav - link to series 2")
        self.assertPattern(
            '<li>.*<a href="%s".*>.*Series 4:.*Miscellaneous.*</a>.*</li>' %
            reverse('fa:series-or-index', kwargs={'id': 'raoul548', 'series_id': 's4'}),
            response.content, "series nav - link to series 4")

        # descriptive info
        self.assertPattern(
            '<h3>Biographical Note</h3>.*<p>.*born March 1.*</p>',
            response.content, "subseries biographical note")
        self.assertPattern(
            '<h3>Scope and Content Note</h3>.*<p>.*letters to family.*</p>.*<p>.*earliest letters.*</p>',
            response.content, "subseries scope & content, 2 paragraphs")
        self.assertContains(
            response,
            '<div><h3>Arrangement Note</h3><p>Arranged by record type.</p></div>',
            html=True)

        # subseries contents
        self.assertPattern(
            '20.*1.*1886-1887', response.content,
            "first content of subseries 1.6")
        self.assertPattern(
            '22.*14.*Journal,.*1888', response.content,
            "sample middle content of subseries 1.6")
        self.assertPattern(
            '22.*23.*1910-1912', response.content,
            "last content of subseries 1.6")

        # top-level ToC on series page should include index link
        self.assertContains(
            response, 'Index of Selected Correspondents',
            msg_prefix="subseries ToC lists index title")
        self.assertContains(
            response, 'href="%s"' % reverse('fa:series-or-index',
                                            kwargs={'id': 'raoul548',
                                                    'series_id': 'index1'}),
            msg_prefix="subseries ToC links to index")
        self.assertContains(
            response, 'Second Index',
            msg_prefix='subseries ToC lists second index title')
        self.assertContains(
            response, 'href="%s"' % reverse('fa:series-or-index',
                                            kwargs={'id': 'raoul548',
                                            'series_id': 'index2'}),
            msg_prefix='subseries ToC links to second index')

    def test_view_subsubseries__raoul_series4_1a(self):
        # NOTE: raoul series 4 broken into sub-sub-series for testing, is not in original finding aid
        subsubseries_url = reverse('fa:series3',
                                   kwargs={'id': 'raoul548',
                                           'series_id': 's4', 'series2_id': '4.1',
                                           'series3_id': '4.1a'})
        response = self.client.get(subsubseries_url)
        expected = 200
        self.assertEqual(
            response.status_code, expected,
            'Expected %s but returned %s for %s' % (expected, response.status_code,
                                                    subsubseries_url))

        # - sub-subseries title
        self.assertPattern(
            '<h2>.*Subseries 4\.1a.*Genealogy.*(?!None).*</h2>',
            response.content, "sub-subseries title displayed, no physdesc")
        # - ead title
        self.assertPattern(
            '<h1[^>]*>.*<a href="%s" rel="contents">\s*RAOUL FAMILY.*Raoul family papers' %
            reverse('fa:findingaid', kwargs={'id': 'raoul548'}),
            response.content, "finding aid title displayed, links to main record page")

        # series nav
        self.assertPattern(
            '<li>.*<a href="%s".*rel="start">.*Series 1:.*Letters and personal papers,.*1865-1982.*</a>.*</li>' %
            reverse('fa:series-or-index', kwargs={'id': 'raoul548', 'series_id': 's1'}),
            response.content, "series nav - series 1 link")
        self.assertPattern(
            '<li>.*<a href="%s.* rel="next">.*Series 2:.*Photographs.*</a>.*</li>' %
            reverse('fa:series-or-index', kwargs={'id': 'raoul548', 'series_id': 's2'}),
            response.content, "series nav - link to series 2")
        self.assertPattern(
            '<li>.*<a href="%s".*>.*Series 4:.*Miscellaneous.*</a>.*</li>' %
            reverse('fa:series-or-index', kwargs={'id': 'raoul548', 'series_id': 's4'}),
            response.content, "series nav - link to series 4")

        # subseries contents
        self.assertPattern('46.*1.*Raoul family journal', response.content,
                           "first content of sub-subseries 4.1a")
        self.assertPattern('46.*2.*Gaston Cesar Raoul', response.content,
                           "last content of sub-subseries 4.1a")

        # series with <head>less scopecontent
        subseries_url = reverse('fa:series2',
                                kwargs={'id': 'raoul548',
                                        'series_id': 's4',
                                        'series2_id': 'subseries2.1'})
        response = self.client.get(subseries_url)
        self.assertContains(response, "Subseries 2.1")
        self.assertContains(response, "Additional drafts and notes")
        # missing section head should not be displayed as "none"
        # FIXME: this is generating a None in the RDFa for some non-obvious reason
        # This only seems to be happening in the unit tests...
        self.assertContains(
            response, "None", 0,
            msg_prefix="series with a section with no head does not display 'None' for heading")
        # breadcrumb link
        self.assertContains(
            response, '<a href="%s">Miscellaneous' %
            reverse('fa:series-or-index', kwargs={'id': 'raoul548', 'series_id': 's4'}),
            1, msg_prefix='should only contain 1 instance of series linked title(breadcrumb)')

    def test_preview_mode(self):
        # test preview mode of all main finding aid views

        # load fixture to preview collection
        fullpath = path.join(exist_fixture_path, 'raoul548.xml')
        self.db.load(open(fullpath, 'r'), settings.EXISTDB_PREVIEW_COLLECTION + '/raoul548.xml',
                     overwrite=True)

        # non-preview page should *NOT* include publish form
        response = self.client.get(reverse('fa:findingaid', kwargs={'id': 'raoul548'}))
        self.assertNotContains(
            response, '<form id="preview-publish" ',
            msg_prefix="non-preview finding aid page should not include publish form")
        # remove published document to make preview errors more obvious
        self.db.removeDocument(settings.EXISTDB_ROOT_COLLECTION + '/raoul548.xml')

        fa_url = reverse('fa-admin:preview:findingaid', kwargs={'id': 'raoul548'})
        response = self.client.get(fa_url)
        expected = 200
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s' %
                         (expected, response.status_code, fa_url))

        ead_url = reverse('fa-admin:preview:eadxml', kwargs={'id': 'raoul548'})
        self.assertContains(response, 'href="%s"' % ead_url)

        series_url = reverse('fa-admin:preview:series-or-index',
                             kwargs={'id': 'raoul548', 'series_id': 's1'})
        self.assertContains(
            response, 'href="%s"' % series_url,
            msg_prefix='preview version of main finding aid should link to series in preview mode')

        subseries_url = reverse('fa-admin:preview:series2',
                                kwargs={'id': 'raoul548', 'series_id': 's1',
                                        'series2_id': 's1.1'})
        self.assertContains(
            response, "href='%s'" % subseries_url,
            msg_prefix='preview version of main finding aid should link to subseries in preview mode')

        index_url = reverse('fa-admin:preview:series-or-index',
                            kwargs={'id': 'raoul548', 'series_id': 'index1'})
        self.assertContains(
            response, 'href="%s"' % index_url,
            msg_prefix='preview version of main finding aid should link to index in preview mode')
        # publish form - requires logging in, really an admin feature - tested in fa_admin.tests

        # load series page
        series_url = reverse('fa-admin:preview:series-or-index',
                             kwargs={'id': 'raoul548', 'series_id': 's1'})
        response = self.client.get(series_url)
        self.assertContains(
            response, 'href="%s"' % fa_url,
            msg_prefix='preview version of series should link to main finding aid page in preview mode')
        self.assertContains(
            response, 'href="%s"' % index_url,
            msg_prefix='preview version of series should link to index in preview mode')

        # clean up
        self.db.removeDocument(settings.EXISTDB_PREVIEW_COLLECTION + '/raoul548.xml')

# **** tests for helper functions for creating series url, list of series/subseries for display in templates

    def test__series_url(self):
        self.assertEqual(reverse('fa:series-or-index', kwargs={'id': 'docid', 'series_id': 's1'}),
                         _series_url('docid', 's1'))
        self.assertEqual(reverse('fa:series2',
                                 kwargs={'id': 'docid', 'series_id': 's1',
                                         'series2_id': 's1.2'}),
                         _series_url('docid', 's1', 's1.2'))
        self.assertEqual(
            reverse('fa:series3', kwargs={'id': 'docid', 'series_id': 's3',
                                          'series2_id': 's3.5', 'series3_id': 's3.5a'}),
            _series_url('docid', 's3', 's3.5', 's3.5a'))

    def test__subseries_links__dsc(self):
        # subseries links for a top-level series that has subseries
        fa = FindingAid.objects.get(eadid='raoul548')
        links = _subseries_links(fa.dsc, url_ids=[fa.eadid])

        self.assert_("Series 1: Letters and personal papers" in links[0])
        self.assert_(
            "href='%s'" % reverse('fa:series-or-index',
                                  kwargs={'id': 'raoul548', 'series_id': 's1'})
            in links[0])
        # nested list for subseries
        self.assert_(isinstance(links[1], ListType))
        self.assert_("Subseries 1.1: William Greene" in links[1][0])
        self.assert_(
            "href='%s'" % reverse('fa:series2', kwargs={'id': 'raoul548',
                                                        'series_id': 's1',
                                                        'series2_id': 's1.1'})
            in links[1][0])

        # second-to-last entry - series 4
        self.assert_("Series 4: Misc" in links[-2])
        self.assert_("href='%s'" % reverse('fa:series-or-index',
                                           kwargs={'id': 'raoul548', 'series_id': 's4'})
                     in links[-2])
        # last entry - series 4 subseries
        self.assert_(isinstance(links[-1], ListType))
        self.assert_("Subseries 4.1:" in links[-1][0])
        # series 4.1 sub-subseries
        self.assert_(isinstance(links[-1][1], ListType))
        self.assert_("Subseries 4.1a:" in links[-1][1][0])

        # url params to add to url (e.g., keyword search terms)
        links = _subseries_links(fa.dsc, url_ids=[fa.eadid],
                                 url_params='?keywords=search+me')
        self.assert_("?keywords=search+me'" in links[0])  # series url
        self.assert_("?keywords=search+me'" in links[1][0])  # subseries url

    def test__subseries_links(self):
        # subseries links for a top-level series that has subseries
        series = Series.objects.also('ead__eadid').get(id='raoul548_s1')
        links = _subseries_links(series)

        self.assertEqual(13, len(links))  # raoul series has subseries 1-13
        self.assert_("href='%s'" % reverse('fa:series2',
                     kwargs={'id': 'raoul548', 'series_id': 's1',
                     'series2_id': 's1.3'}) in links[2])
        self.assert_('Subseries 1.1: William Greene' in links[0])
        self.assert_("href='%s'" % reverse('fa:series2',
                     kwargs={'id': 'raoul548', 'series_id': 's1',
                     'series2_id': 's1.1'}) in links[0])
        self.assert_('Subseries 1.2: Mary Wadley' in links[1])
        self.assert_("href='%s'" % reverse('fa:series2',
                     kwargs={'id': 'raoul548', 'series_id': 's1',
                     'series2_id': 's1.2'}) in links[1])
        self.assert_('Subseries 1.3: Sarah Lois' in links[2])
        self.assert_("href='%s'" % reverse('fa:series2',
                     kwargs={'id': 'raoul548', 'series_id': 's1',
                     'series2_id': 's1.3'}) in links[2])
        self.assert_('Subseries 1.13: Norman Raoul' in links[-1])
        self.assert_("href='%s'" % reverse('fa:series2',
                     kwargs={'id': 'raoul548', 'series_id': 's1',
                     'series2_id': 's1.13'}) in links[-1])

        series = Series.objects.get(id='raoul548_s1')
        # should get exception when top-level ead id is not available
        self.assertRaises(Exception, _subseries_links, series)

    def test__subseries_links_nested(self):
        # subseries links for a top-level series that has subseries with sub-subseries (nested list)
        series = Series.objects.also('ead__eadid').get(id='raoul548_s4')
        links = _subseries_links(series)

        self.assert_("Subseries 4.1: Misc" in links[0])
        self.assert_("href='%s'" % reverse('fa:series2',
                     kwargs={'id': 'raoul548', 'series_id': 's4',
                     'series2_id': '4.1'}) in links[0])
        self.assert_(isinstance(links[1], ListType))
        self.assert_("Subseries 4.1a: Genealogy" in links[1][0])
        self.assert_("href='%s'" % reverse('fa:series3',
                     kwargs={'id': 'raoul548', 'series_id': 's4',
                     'series2_id': '4.1', 'series3_id': '4.1a'}) in links[1][0])
        self.assert_("Subseries 4.1b: Genealogy part 2" in links[1][1])
        self.assert_("href='%s'" % reverse('fa:series3',
                     kwargs={'id': 'raoul548', 'series_id': 's4',
                     'series2_id': '4.1', 'series3_id': '4.1b'}) in links[1][1])

    def test__subseries_links_c02(self):
        # subseries links when not starting at c01 level
        series = Series2.objects.also('ead__eadid', 'series__id').get(id='raoul548_4.1')
        links = _subseries_links(series)

        self.assertEqual(2, len(links))     # test doc has two c03 subseries
        self.assert_("Subseries 4.1a: Genealogy" in links[0])
        self.assert_("href='%s'" % reverse('fa:series3',
                     kwargs={'id': 'raoul548', 'series_id': 's4',
                     'series2_id': '4.1', 'series3_id': '4.1a'}) in links[0])
        self.assert_("Subseries 4.1b: Genealogy part 2" in links[1])
        self.assert_("href='%s'" % reverse('fa:series3',
                     kwargs={'id': 'raoul548', 'series_id': 's4',
                     'series2_id': '4.1', 'series3_id': '4.1b'}) in links[1])

        # c02 retrieved without parent c01 id should get an exception
        series = Series2.objects.also('ead__eadid').get(id='raoul548_4.1')
        self.assertRaises(Exception, _subseries_links, series)

    def test__subseries_links_c03(self):
        # c03 retrieved without parent c01 id should get an exception
        series = Series3.objects.also('ead__eadid').get(id='raoul548_4.1a')
        self.assertRaises(Exception, _subseries_links, series)

        # c03 with series but not subseries id - still exception
        series = Series3.objects.also('ead__eadid', 'series__id').get(id='raoul548_4.1a')
        self.assertRaises(Exception, _subseries_links, series)

        # all required parent ids - no exception
        series = Series3.objects.also('ead__eadid', 'series__id', 'series2__id').get(id='raoul548_4.1a')
        self.assertEqual([], _subseries_links(series))

    def test__subseries_links_anchors(self):
        # subseries links  - generate same-page anchors instead of full urls
        fa = FindingAid.objects.get(eadid='raoul548')
        links = _subseries_links(fa.dsc, url_ids=[fa.eadid], url_callback=_series_anchor)

        self.assert_("Series 1: Letters and personal papers" in links[0])
        self.assert_("href='#s1'" in links[0])
        self.assert_("rel='section dcterms:hasPart'" in links[0])
        # subseries
        self.assert_("href='#s1.1'" in links[1][0])
        self.assert_("rel='subsection dcterms:hasPart'" in links[1][0])

    # skip the printable test if XSLFO is not configured (i.e., if FOP cannot be installed)
    @unittest.skipIf(not settings.XSLFO_PROCESSOR, 'XSL-FO processor not set')
    def test_printable_fa(self):
        # using 'full' html version of pdf for easier testing
        fullfa_url = reverse('fa:full-findingaid', kwargs={'id': 'raoul548'})
        response = self.client.get(fullfa_url)
        expected = 200
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s' %
                         (expected, response.status_code, fullfa_url))
        # publication infor
        self.assertPattern(
            'Emory University.*Manuscript, Archives, and Rare Book Library.*Atlanta, GA 30322',
            response.content,
            "publication statement included")

        # NOTE: using same section templates as other views, which are tested more thoroughly above
        # here, just checking that appropriate sections are present

        # description
        self.assertContains(response, "Descriptive Summary")
        # controlaccess not included in print copy
        self.assertContains(response, "Selected Search Terms", 0)
        # series list, and all series down to c03 level
        self.assertContains(response, "Description of Series")
        # series links are anchors in the same page
        self.assertPattern('<a href=\'#s1\.10\' rel=\'subsection dcterms:hasPart\'>Subseries 1.10', response.content)
        self.assertPattern('<h2 class="series">.*Series 1 .*Letters and personal papers,.* 1865-1982.*</h2>', response.content)
        self.assertPattern('<h2 class="subseries">.*Subseries 1.2 .*Mary Wadley Raoul papers,.* 1865-1936.*</h2>', response.content)
        # index
        self.assertContains(response, "Index of Selected Correspondents")
        # second index
        self.assertContains(response, "Second Index")

        # simple finding aid with no subseries - should have container list
        response = self.client.get(reverse('fa:full-findingaid', kwargs={'id': 'leverette135'}))
        self.assertContains(
            response, "Container List",
            msg_prefix="finding aid with no subseries should include container list in printable mode")

        # minimal testing on actual PDF
        pdf_url = reverse('fa:printable', kwargs={'id': 'raoul548'})
        response = self.client.get(pdf_url)
        expected = 'application/pdf'
        self.assertEqual(response['Content-Type'], expected,
                         "Expected '%s' but returned '%s' for %s mimetype" %
                         (expected, response['Content-Type'], pdf_url))
        expected = 'inline; filename=raoul548.pdf'
        self.assertEqual(response['Content-Disposition'], expected,
                         "Expected '%s' but returned '%s' for %s content-disposition" %
                         (expected, response['Content-Disposition'], pdf_url))

        # test the XSL-FO used to generate PDF
        # - if a template changes in a way that breaks valid XSL-FO generation, we need to catch it
        xslfo_url = reverse('fa:xslfo', kwargs={'id': 'raoul548'})
        response = self.client.get(xslfo_url)
        # if XSL-FO is not valid xml, etree will not be able to parse
        xslfo = etree.fromstring(response.content)
        self.assert_(isinstance(xslfo, etree._Element))
        # NOTE: currently cannot validate XSL-FO
        # - there is no official XSL-FO schema or DTD; available unofficial
        # schemas do not include fo:bookmark (which is part of XSL-FO v1.1)

    def test_eadxml(self):
        nonexistent_ead = reverse('fa:eadxml', kwargs={'id': 'nonexistent'})
        response = self.client.get(nonexistent_ead)
        expected = 404
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for nonexistent EAD at %s'
                         % (expected, response.status_code, nonexistent_ead))
        xml_url = reverse('fa:eadxml', kwargs={'id': 'abbey244'})
        response = self.client.get(xml_url)
        expected = 200
        self.assertEqual(response.status_code, expected, 'Expected %s but returned %s for %s' %
                        (expected, response.status_code, xml_url))
        expected = 'application/xml'
        self.assertEqual(response['Content-Type'], expected,
                         "Expected '%s' but returned '%s' for %s mimetype" %
                         (expected, response['Content-Type'], xml_url))
        self.assertContains(response, 'identifier="ark:/25593/1fx')

        # load httpresponse body into an XmlObject to compare with findingaid doc
        ead = load_xmlobject_from_string(response.content)
        abbey = FindingAid.objects.get(eadid='abbey244')
        self.assertEqual(
            ead.serialize(), abbey.serialize(),
            "response content should be the full, valid XML content of the requested EAD document")

    def test_content_negotiation(self):
        url = reverse('fa:findingaid', kwargs={'id': 'raoul548'})

        # normal request
        response = self.client.get(url)
        self.assertEqual(response['Content-Type'], "text/html; charset=utf-8", "Should return html")

        # request application/xml
        response = self.client.get(url, HTTP_ACCEPT="application/xml")
        self.assertEqual(response['Content-Type'], "application/xml", "Should return xml")

        # request text/xml
        response = self.client.get(url, HTTP_ACCEPT="text/xml")
        self.assertEqual(response['Content-Type'], "application/xml", "Should return xml")

    def test_return_to_search_or_browse(self):
        #No session variables set so Cache-Control should not be set
        url = reverse('fa:findingaid', kwargs={'id': 'raoul548'})
        response = self.client.get(url)
        session = self.client.session
        last_search = session.get("last_search", None)
        self.assertFalse(last_search)
        self.assertFalse(response.get('Cache-Control', None),
                         "Cache-Control should not be set since there are no session variables set")
        self.assertNotContains(response, 'Return to Browse',
                               msg_prefix="No return to browse link should appear since there are no session variables set")

        #With last_search set in search
        #Calling search view first to set session info to simulate a user searching
        search_url = reverse('fa:search')
        self.client.get(search_url, {'keywords': 'raoul'})

        url = reverse('fa:findingaid', kwargs={'id': 'raoul548'})
        response = self.client.get(url)
        session = self.client.session
        last_search = session.get("last_search", None)
        self.assertTrue(last_search)
        self.assertEqual(last_search['txt'], "Return to Search Results", 'test to make sure the search view set the session')

        self.assertTrue(
            response['Cache-Control'],
            "Cache-Control should be set since there are session variables set")
        self.assertEqual(
            response['Cache-Control'], "private",
            "value should be private")
        self.assertContains(
            response, '<a href="%s?keywords=raoul&amp;page=1">Return to Search Results</a>'
            % (reverse('fa:search')), msg_prefix="retun to search link should exist")

        # With last_search set in browse
        # Calling title-by-letter view first to set session info to simulate a user
        letter = "R"
        browse_url = reverse('fa:titles-by-letter', kwargs={'letter': letter})
        self.client.get(browse_url)

        url = reverse('fa:findingaid', kwargs={'id': 'raoul548'})
        response = self.client.get(url)
        session = self.client.session
        last_search = session.get("last_search", None)
        self.assertTrue(last_search)
        self.assertEqual(last_search['txt'], "Return to Browse Results", 'test to make sure the browse view set the session')

        self.assertTrue(response['Cache-Control'], "Cache-Control should be set since there are session variables set")
        self.assertEqual(response['Cache-Control'], "private", "value should be private")
        self.assertContains(
            response, '<a href="%s?page=1">Return to Browse Results</a>'
            % (reverse('fa:titles-by-letter', kwargs={'letter': letter})),
            msg_prefix="retun to browse link should exist")

    def test_short_ids(self):
        # urls for series/index should use short-form ids (tested above, throughout)
        # request on url with long-form ids should get a permanent redirect to short-form

        # - series
        long_id_url = reverse('fa:series-or-index',  kwargs={'id': 'raoul548',
                                                             'series_id': 'raoul548_s4'})
        short_id_url = reverse('fa:series-or-index',  kwargs={'id': 'raoul548',
                                                              'series_id': 's4'})
        response = self.client.get(long_id_url)
        self.assertRedirects(response, short_id_url, status_code=301)

        # - series2
        long_id_url = reverse('fa:series2', kwargs={'id': 'raoul548',
                                                    'series_id': 'raoul548_s1',
                                                    'series2_id': 'raoul548_s1.3'})
        short_id_url = reverse('fa:series2', kwargs={'id': 'raoul548',
                                                     'series_id': 's1',
                                                     'series2_id': 's1.3'})
        response = self.client.get(long_id_url)
        self.assertRedirects(response, short_id_url, status_code=301)

        # - series3
        long_id_url = reverse('fa:series3', kwargs={'id': 'raoul548',
                                                    'series_id': 'raoul548_s4',
                                                    'series2_id': 'raoul548_4.1',
                                                    'series3_id': 'raoul548_4.1b'})
        short_id_url = reverse('fa:series3', kwargs={'id': 'raoul548',
                                                     'series_id': 's4',
                                                     'series2_id': '4.1',
                                                     'series3_id': '4.1b'})
        response = self.client.get(long_id_url)
        self.assertRedirects(response, short_id_url, status_code=301)

        # index
        long_id_url = reverse('fa:series-or-index',  kwargs={'id': 'raoul548',
                                                             'series_id': 'raoul548_index1'})
        short_id_url = reverse('fa:series-or-index',  kwargs={'id': 'raoul548',
                                                              'series_id': 'index1'})
        response = self.client.get(long_id_url)
        self.assertRedirects(response, short_id_url, status_code=301)

        # mixed long and short ids, series3
        long_id_url = reverse('fa:series3', kwargs={'id': 'raoul548',
                                                    'series_id': 's4',
                                                    'series2_id': 'raoul548_4.1',
                                                    'series3_id': '4.1b'})
        short_id_url = reverse('fa:series3', kwargs={'id': 'raoul548',
                                                     'series_id': 's4',
                                                     'series2_id': '4.1',
                                                     'series3_id': '4.1b'})
        response = self.client.get(long_id_url)
        self.assertRedirects(response, short_id_url, status_code=301)

        # invalid id should not redirect
        invalid_id_url = reverse('fa:series-or-index',  kwargs={'id': 'raoul548',
                                                                'series_id': 'bogusid_s4'})
        response = self.client.get(invalid_id_url)
        expected, got = 404, response.status_code
        self.assertEqual(expected, got, 'Expected %s but returned %s for %s' %
                        (expected, got, invalid_id_url))


class FullTextFaViewsTest(TestCase):
    fixtures = ['user']
    # test for views that require eXist full-text index
    exist_fixtures = {'index': exist_index_path,
                      'directory': exist_fixture_path}

    def test_search(self):
        search_url = reverse('fa:search')
        response = self.client.get(search_url, {'keywords': 'raoul'})
        session = self.client.session
        expected = 200
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s' %
                         (expected, response.status_code, search_url))
        last_search = session.get("last_search", None)
        self.assertTrue(last_search)
        self.assertEqual("%s?keywords=raoul&page=1" % (search_url), last_search['url'])

        self.assertPattern(
            "<p[^>]*>Search results for.*raoul.*</p>", response.content,
            msg_prefix='search results include search term')
        self.assertContains(
            response, "1 finding aid found",
            msg_prefix='search for "raoul" returns one finding aid')
        self.assertContains(
            response, reverse('fa:findingaid', kwargs={'id': 'raoul548'}),
            msg_prefix='search for raoul includes link to raoul finding aid')
        self.assertContains(
            response, "<div class=\"relevance\">",
            msg_prefix='search results include relevance indicator')
        self.assertContains(
            response, '%s?keywords=raoul' % reverse('fa:findingaid', kwargs={'id': 'raoul548'}),
            msg_prefix='link to finding aid includes search terms')

        self.assertContains(
            response, '<meta name="robots" content="noindex,nofollow"',
            msg_prefix="search results page includes robots directives - noindex, nofollow")

        response = self.client.get(search_url, {'keywords': 'family papers'})
        expected = 200
        self.assertEqual(
            response.status_code, expected,
            'Expected %s but returned %s for %s' %
            (expected, response.status_code, search_url))
        self.assertPattern("<p[^>]*>Search results for.*family papers.*</p>", response.content)
        self.assertContains(
            response, "5 finding aids found",
            msg_prefix='search for "family papers" should return 5 test finding aids')
        self.assertContains(
            response, "Fannie Lee Leverette scrapbooks",
            msg_prefix='search for "family papers" should include Leverette')
        self.assertPattern(
            "Raoul .*family.* .*papers", response.content,   # exist-match highlighting
            msg_prefix='search for "family papers" should include raoul')
        self.assertPattern(
            "Bailey and Thurman families .*papers", response.content,
            msg_prefix='search for "family papers" should include bailey')
        self.assertContains(
            response, "Abbey Theatre collection",
            msg_prefix='search for "family papers" should include abbey theatre')
        self.assertContains(
            response, "Pomerantz, Gary M.",
            msg_prefix='search for "family papers" should include pomerantz')
        self.assertContains(
            response, "<div class=\"relevance\">", 5,
            msg_prefix='search results return one relevance indicator for each match')
        self.assertContains(
            response, '%s?keywords=family+papers' % reverse('fa:findingaid', kwargs={'id': 'leverette135'}),
            msg_prefix='link to finding aid includes search terms')

        response = self.client.get(search_url, {'keywords': 'nonexistentshouldmatchnothing'})
        expected = 200
        self.assertEqual(response.status_code, expected,
                         'Expected %s but returned %s for %s' %
                         (expected, response.status_code, search_url))
        self.assertContains(
            response, "No finding aids matched",
            msg_prefix='search for nonexistent term should indicate no matches found')

        response = self.client.get(search_url, {'dao': 'on'})
        leverette_url = reverse('fa:findingaid', kwargs={'id': 'leverette135'})
        abbey_url = reverse('fa:findingaid', kwargs={'id': 'abbey244'})
        self.assertContains(response, leverette_url,
            msg_prefix='search for digital resources should include Leverette')
        self.assertNotContains(response, abbey_url,
            msg_prefix='search for digital resources should not include abbey (internal dao only)')

        # when logged in as an admin, documents with internal dao should also be returned

        self.client.login(username='marbl', password='marbl')
        response = self.client.get(search_url, {'dao': 'on'})
        self.assertContains(response, abbey_url,
            msg_prefix='search for digital resources should include abbey (internal dao only)')

    def test_search__exact_phrase(self):
        search_url = reverse('fa:search')
        # search term missing close quote - query syntax error
        response = self.client.get(search_url,
                                   {'keywords': '"georgia'})

        messages = [str(msg) for msg in response.context['messages']]
        # expected http status code ?
        self.assert_("search query could not be parsed" in messages[0],
                     "query parse error message present in response context")
        expected, got = 400, response.status_code
        self.assertEqual(expected, got,
                         'Expected %s but returned %s for %s with invalid exact phrase search' %
                         (expected, got, search_url))

        # exact phrase
        response = self.client.get(search_url,
                                   {'keywords': '"Abbey Theatre organized in 1904"'})
        self.assertContains(
            response, 'Abbey Theatre collection',
            msg_prefix='search results include Abbey Theatre for exact phrase from Abbey Theatre bioghist')
        self.assertContains(
            response, '1 finding aid found',
            msg_prefix='only one search result for exact phrase from Abbey Theatre bioghist')

    def test_search__wildcard(self):
        search_url = reverse('fa:search')
        # wildcard search
        response = self.client.get(search_url, {'keywords': 'Abb?y Theat*'})

        self.assertContains(
            response, 'Abbey Theatre collection',
            msg_prefix='search results include Abbey Theatre for wildcard search "Abb?y Theat*"')

        # don't know of any error cases that could happen with wildcards...

    def test_subject_search(self):
        search_url = reverse('fa:search')
        response = self.client.get(search_url, {'subject': 'Scripts.'})
        session = self.client.session

        last_search = session.get("last_search", None)
        self.assertTrue(last_search)
        self.assertEqual("%s?page=1&subject=Scripts." % (search_url), last_search['url'])

        self.assertPattern(
            "<p[^>]*>Search results for.*subject:.*Scripts\..*</p>", response.content,
            msg_prefix='search results include subject search term')
        self.assertContains(
            response, "1 finding aid found",
            msg_prefix='search for "Scripts" in subject returns one finding aid')
        self.assertContains(
            response, reverse('fa:findingaid', kwargs={'id': 'abbey244'}),
            msg_prefix='search for "subject:Scripts" includes link to abbey244 finding aid')
        self.assertNotContains(
            response, "<div class=\"relevance\">",
            msg_prefix='search for subject only does not include relevance indicator')

        # keyword now optional - no search terms should be an invalid form
        response = self.client.get(search_url, {'subject': '', 'keywords': ''})
        self.assertContains(response, 'Please enter search terms or choose a repository.')

    def test_repository_search(self):
        search_url = reverse('fa:search')
        # FIXME: this depends on repository choices cache matching test data...
        response = self.client.get(search_url, {'keywords': 'papers',
                                   'repository': '"University Archives"'})
        session = self.client.session

        last_search = session.get("last_search", None)
        self.assertTrue(last_search)
        self.assertEqual(
            search_url + "?keywords=papers&page=1&repository=%22University+Archives%22",
            last_search['url'])

        # one fixture has been modified to have a different repository
        self.assertPattern(
            "<p[^>]*>Search results for.*repository:.*University Archives.*</p>", response.content,
            msg_prefix='search results include repository filter')
        self.assertContains(
            response, "1 finding aid found",
            msg_prefix='search for "papers" & repository "University Archives" returns one finding aid')
        self.assertContains(
            response, reverse('fa:findingaid', kwargs={'id': 'bailey807'}),
            msg_prefix='search for "papers" & repository "University Archives" includes link to bailey807 finding aid')
        self.assertNotContains(
            response, reverse('fa:findingaid', kwargs={'id': 'abbey244'}),
            msg_prefix='search for "papers" & repository "University Archives" does not include non-UA finding aid')

        #Attempting to demonstrate the the repo only search returns sorted  results
        response = self.client.get(search_url, {'repository': '"Manuscript, Archives, and Rare Book Library"'})
        self.assertPattern("Abbey Theatre\..*Adams.*Leverette.*Pitts.*Pomerantz.*Raoul", response.content,
                           msg_prefix='repository search returns results in alphabetical order')

    def test_search__boolean(self):
        search_url = reverse('fa:search')

        #incorrect use of boolean
        response = self.client.get(search_url, {'keywords': 'AND Abbey'})
        self.assertContains(
            response,
            "Your search query could not be parsed.  Please revise your search and try again.",
            status_code=400)

        #OR operator
        response = self.client.get(search_url, {'keywords': 'Abbey or raoul'})
        self.assertContains(response, "<b>Abbey OR raoul</b>")  # converted or to OR
        self.assertContains(response, "Raoul family.")  # Raoul record
        self.assertContains(response, "Abbey Theatre.")  # Abby record

        #NOT operator
        response = self.client.get(search_url, {'keywords': 'Emory'})
        self.assertContains(response, "7 finding aids found")  # not using NOT yet
        self.assertContains(response, "Abbey Theatre.")  # Theatre record

        response = self.client.get(search_url, {'keywords': 'Emory not Theatre'})
        self.assertContains(response, "<b>Emory NOT Theatre</b>")  # converted not to NOT
        self.assertContains(response, "5 finding aids found")  # using NOT
        self.assertNotContains(response, "Abbey Theatre")  # Theatre record not in results

        # AND operator
        response = self.client.get(search_url, {'keywords': 'Bailey and Theatre'})
        self.assertContains(response, "<b>Bailey AND Theatre</b>")  # converted and to AND
        self.assertContains(response, "1 finding aid found")  # using AND
        self.assertContains(
            response,
            "Bailey and Thurman families papers, circa 1882-1995")  # Bailey record in resulsts

    def test_search__grouping(self):
        search_url = reverse('fa:search')

        # missing parentheses
        response = self.client.get(search_url, {'keywords': '(Abbey'})
        self.assertContains(
            response,
            "Your search query could not be parsed.  Please revise your search and try again.",
            status_code=400)

        #missing quote
        response = self.client.get(search_url, {'keywords': 'Abbey"'})
        self.assertContains(
            response,
            "Your search query could not be parsed.  Please revise your search and try again.",
            status_code=400)

        # use grouping to narrow search results
        response = self.client.get(search_url, {'keywords': 'Emory or scripts'})
        self.assertContains(response, "<b>Emory OR scripts</b>")  # converted or to OR
        self.assertContains(response, "7 finding aids found")
        self.assertContains(response, "Pitts v. Freeman")  # Should be returned before search is narrowed
        self.assertContains(response, "Raoul family.")  # Should be returned before search is narrowed

        response = self.client.get(search_url, {'keywords': '(Emory or scripts) not (files and school)'})
        self.assertContains(response, "<b>(Emory OR scripts) NOT (files AND school)</b>")  # converted or and not to OR AND NOT
        self.assertContains(response, "5 finding aids found")
        self.assertNotContains(response, "Pitts v. Freeman")  # Should not be returned after search is narrowed
        self.assertNotContains(response, "Raoul family.")  # Should not be returned after search is narrowed

    def test_view_highlighted_fa(self):
        # view a finding aid with search-term highlighting
        fa_url = reverse('fa:findingaid', kwargs={'id': 'raoul548'})
        response = self.client.get(fa_url, {'keywords': 'raoul georgia'})
        self.assertContains(
            response,
            '%s?keywords=raoul+georgia#descriptive_summary' %
            reverse('fa:findingaid',  kwargs={'id': 'raoul548'}),
            msg_prefix="descriptive summary anchor-link includes search terms")
        self.assertContains(
            response,
            '%s?keywords=raoul+georgia' %
            reverse('fa:series-or-index',  kwargs={'id': 'raoul548', 'series_id': 's4'}),
            msg_prefix="series link includes search terms")
        self.assertContains(
            response,
            '%s?keywords=raoul+georgia' %
            reverse('fa:series-or-index',  kwargs={'id': 'raoul548', 'series_id': 'index1'}),
            msg_prefix="index link includes search terms")
        self.assertContains(
            response,
            '%s?keywords=raoul+georgia' %
            reverse('fa:series2', kwargs={'id': 'raoul548', 'series_id': 's1',
                                          'series2_id': 's1.3'}),
            msg_prefix="subseries link includes search terms")

        self.assertContains(
            response, '<meta name="robots" content="noindex,nofollow"',
            msg_prefix="highlighted finding aid includes robots directives - noindex, nofollow")
        self.assertContains(
            response, '<link rel="canonical" href="%s"' % fa_url,
            msg_prefix="highlighted finding aid includes link to canonical finding aid url")

        # highlighting
        self.assertContains(
            response, '<span class="exist-match">Raoul</span>',
            msg_prefix="search terms are highlighted on main finding aid page")
        self.assertContains(
            response, '<span class="exist-match">Raoul</span>, Eleanore',
            msg_prefix="search terms in control access terms are highlighted")

        # match count in table of contents
        self.assertPattern(
            r'<li>.*Descriptive Summary.*4 matches.*</li>', response.content,
            msg_prefix="descriptive summary has match count in ToC")
        self.assertPattern(
            r'<li>.*Collection Description.*51 matches.*</li>', response.content,
            msg_prefix="collection description has match count in ToC")
        self.assertPattern(
            r'<li>.*Selected Search Terms.*30 matches.*</li>', response.content,
            msg_prefix="selected search terms has match count in ToC")

        # match count for non-series document
        fa_url = reverse('fa:findingaid', kwargs={'id': 'leverette135'})
        response = self.client.get(fa_url, {'keywords': '"hickory hill"'})
        self.assertPattern(
            r'<li>.*Container List.*1 match.*</li>', response.content,
            msg_prefix="container list has match count in ToC")

    def test_view_highlighted_series(self):
        # single series in a finding aid, with search-term highlighting
        # NOTE: series, subseries, and index all use the same view
        series_url = reverse('fa:series-or-index',
                             kwargs={'id': 'raoul548', 'series_id': 's4'})
        response = self.client.get(series_url, {'keywords': 'raoul georgia'})
        self.assertContains(
            response,
            '%s?keywords=raoul+georgia' %
            reverse('fa:findingaid',  kwargs={'id': 'raoul548'}),
            msg_prefix="link back to main FA page includes search terms")
        self.assertContains(
            response,
            '%s?keywords=raoul+georgia' %
            reverse('fa:series-or-index',  kwargs={'id': 'raoul548', 'series_id': 's1'}),
            msg_prefix="link to other series includes search terms")
        self.assertContains(
            response,
            '%s?keywords=raoul+georgia' %
            reverse('fa:series-or-index',  kwargs={'id': 'raoul548', 'series_id': 'index1'}),
            msg_prefix="index link includes search terms")
        self.assertContains(
            response,
            '%s?keywords=raoul+georgia' %
            reverse('fa:series2', kwargs={'id': 'raoul548', 'series_id': 's4',
                                          'series2_id': '4.1'}),
            msg_prefix="subseries link includes search terms")

        self.assertContains(
            response, '<meta name="robots" content="noindex,nofollow"',
            msg_prefix="highlighted finding aid series includes robots directives - noindex, nofollow")
        self.assertContains(
            response, '<link rel="canonical" href="%s"' % series_url,
            msg_prefix="highlighted finding aid series includes link to canonical url")

        # highlighting
        self.assertContains(
            response, '<span class="exist-match">Raoul</span>',
            msg_prefix="search terms are highlighted on series page")
        self.assertContains(
            response, 'genealogy, the <span class="exist-match">Raoul</span> mansion',
            msg_prefix="search terms in scope/content note are highlighted")

        # match count in table of contents
        self.assertPattern(
            r'<li>.*Descriptive Summary.*4 matches.*</li>', response.content,
            msg_prefix="descriptive summary has match count in ToC")
        self.assertPattern(
            r'<li>.*Collection Description.*51 matches.*</li>', response.content,
            msg_prefix="collection description has match count in ToC")
        self.assertPattern(
            r'<li>.*Selected Search Terms.*30 matches.*</li>', response.content,
            msg_prefix="selected search terms has match count in ToC")

        # series 3 - box/folder/content
        series_url = reverse('fa:series-or-index',
                             kwargs={'id': 'raoul548', 'series_id': 's3'})
        response = self.client.get(series_url, {'keywords': 'raoul georgia'})
        self.assertContains(
            response, 'W. G. <span class="exist-match">Raoul</span> estate papers',
            msg_prefix="search terms in box/folder section headings are highlighted")
        self.assertContains(
            response, '<span class="exist-match">Raoul</span> Heirs, Inc.',
            msg_prefix="search terms in box/folder contents are highlighted")

        # search terms not in current series
        series_url = reverse('fa:series-or-index',
                             kwargs={'id': 'raoul548', 'series_id': 's3'})
        response = self.client.get(series_url, {'keywords': 'notinthistext'})
        self.assertContains(
            response, 'Financial and legal papers',
            msg_prefix="series without search terms is still returned normally")

    def test_view_highlighted_subseries(self):
        # single subseries in a finding aid, with search-term highlighting
        series_url = reverse('fa:series2', kwargs={'id': 'raoul548',
                             'series_id': 's1', 'series2_id': 's1.1'})
        response = self.client.get(series_url, {'keywords': 'raoul georgia'})
        self.assertContains(
            response, '<link rel="canonical" href="%s"' % series_url,
            msg_prefix="highlighted finding aid subseries includes link to canonical url")

        # highlighting
        self.assertContains(
            response, '<span class="exist-match">Raoul</span>',
            msg_prefix="search terms are highlighted on subseries page")
         # search terms not in current subseries
        response = self.client.get(series_url, {'keywords': 'notinthistext'})
        self.assertContains(
            response, 'Photographs',
            msg_prefix="subseries without search terms is still returned normally")

    def test_view_highlighted_index(self):
        # single index in a finding aid, with search-term highlighting
        index_url = reverse('fa:series-or-index',
                            kwargs={'id': 'raoul548', 'series_id': 'index1'})
        response = self.client.get(index_url, {'keywords': 'raoul georgia'})
        self.assertContains(
            response, '<link rel="canonical" href="%s"' % index_url,
            msg_prefix="highlighted finding aid index includes link to canonical url")

        # highlighting
        self.assertContains(
            response, '<span class="exist-match">Georgia</span>',
            msg_prefix="search terms are highlighted on index page")
        self.assertContains(
            response, '<span class="exist-match">Georgia</span> Institute of Technology',
            msg_prefix="search terms in index entry headings are highlighted")
        self.assertContains(
            response, 'Peacock School, Atlanta, <span class="exist-match">Georgia</span>',
            msg_prefix="search terms in index references are highlighted")
         # search terms not in index
        response = self.client.get(index_url, {'keywords': 'notinthistext'})
        self.assertContains(
            response, 'Index of Selected Correspondents',
            msg_prefix="index without search terms is still returned normally")

    @override_settings(REQUEST_MATERIALS_URL='http://example.com',
        REQUEST_MATERIALS_REPOS = ['Manuscript, Archives, and Rare Book Library'])
    def test_document_search(self):
        search_url = reverse('fa:singledoc-search', kwargs={'id': 'raoul548'})
        response = self.client.get(search_url, {'keywords': 'correspondence'})

        # FIXME:  sometimes the counts are doubled for no apparent reason
        # (two copies of fixture document loaded?)
        # TODO: revise document search to use document(...) instead of collection()
        # - should be faster, and will probably also help this

        self.assertContains(
            response, "Search results for : <b>correspondence</b>",
            msg_prefix='search results include search term')
        self.assertContains(
            response, "22 matches found",
            msg_prefix='search for "correspondence" in raoul548 matches 44 items')
        # box/folder/contents headings should display once for each series
        self.assertContains(
            response, "Box", 4,
            msg_prefix='"Box" heading appears once for each series match')
        self.assertContains(
            response, "Folder", 4,
            msg_prefix='"Folder" heading appears once for each series match')

        # series from fixture with matches:  s1.1, 4, 4.1b
        # - series url & label
        series_url = reverse('fa:series-or-index',
                             kwargs={'id': 'raoul548', 'series_id': 's4'})
        self.assertContains(
            response, series_url,
            msg_prefix='link to series with matches (series 4) is in response')
            # should be displayed once for every subseries with a match
        self.assertContains(
            response, 'Series 4: Miscellaneous',
            msg_prefix='label for series with matches (4) is displayed')
        # - subseries url & label
        self.assertContains(
            response, reverse('fa:series2',
                              kwargs={'id': 'raoul548', 'series_id': 's1',
                                      'series2_id': 's1.1'}),
            count=1, msg_prefix='link to subseries with matches (1.1) occurs once')
        self.assertContains(
            response, 'Subseries 1.1: William Greene',
            msg_prefix='label for series with matches (1.1) is displayed')
        # - label for subseries items includes series
        series_url = reverse('fa:series-or-index',
                             kwargs={'id': 'raoul548', 'series_id': 's1'})
        self.assertContains(
            response, series_url,
            msg_prefix='link to series (1) with subseries matches (1.1) is in response')
        self.assertContains(
            response, 'Series 1: Letters and personal papers',
            msg_prefix='label for series (1) with subseries matches (1.1) is in response')

        # - sub-subseries url & label
        self.assertContains(
            response, reverse('fa:series3',
                              kwargs={'id': 'raoul548', 'series_id': 's4',
                                      'series2_id': '4.1', 'series3_id': '4.1b'}),
            count=1, msg_prefix='link to sub-subseries with matches (4.1b) occurs once')
        self.assertContains(
            response, 'Subseries 4.1b: Genealogy part 2',
            msg_prefix='label for subseries with matches (4.1b) is displayed')
        # - label for sub-subseries includes subseries
        self.assertContains(
            response, reverse('fa:series2',
                              kwargs={'id': 'raoul548', 'series_id': 's4',
                                      'series2_id': '4.1'}),
            msg_prefix='matches in sub-subseries links to subseries')
        self.assertContains(
            response, 'Subseries 4.1: Miscellaneous,',
            msg_prefix='label for subseries with matches (4.1) is displayed')

        self.assertContains(
            response, reverse('fa:findingaid', kwargs={'id': 'raoul548'}),
            msg_prefix='search within raoul48 includes link to main finding aid page')

        self.assertContains(
            response, '<meta name="robots" content="noindex,nofollow"',
            msg_prefix="single-document search results page includes robots directives - noindex, nofollow")

        # links to series and main finding aid should include search terms
        self.assertContains(
            response, '%s?keywords=correspondence' %
            reverse('fa:findingaid', kwargs={'id': 'raoul548'}),
            msg_prefix='links to finding aid series include search terms')

        # ead should be requestable from series
        # (testing that response includes enough data for requestable method)
        self.assertTrue(response.context['ead'].requestable(),
            'Finding aid should be requestable from document search page')

        # no matches
        response = self.client.get(search_url, {'keywords': 'bogus'})
        self.assertContains(
            response, "No matches found",
            msg_prefix='search for "bogus" in raoul548 displays no matches')

        # bad query
        #   NOTE: patching localsettings; if the timeout is set to low here, we
        #   get a timeout error instead of the expected unparsable query error
        with patch.object(settings, 'EXISTDB_TIMEOUT', new=30):
            response = self.client.get(search_url, {'keywords': '"incomplete phrase'})
        # sets status code to 400 bad request
        self.assertContains(
            response, "No matches found", status_code=400,
            msg_prefix='unparse-able search in raoul548 displays no matches')
        messages = [str(msg) for msg in response.context['messages']]
        self.assert_(
            'search query could not be parsed.' in messages[0],
            'user sees a message about error parsing query')
        self.assertNotContains(
            response, '?keywords="incomplete phrase', status_code=400,
            msg_prefix='links do not include invalid query')

        # no query
        response = self.client.get(search_url, {'keywords': ''})
        self.assertContains(
            response, "No matches found",
            msg_prefix='No matches found when form is submitted with no search terms')
        messages = [str(msg) for msg in response.context['messages']]
        self.assert_(
            'Please enter a search term' in messages[0],
            'user sees a message requesting them to enter a search term when ' +
            'form is submitted with no search terms')

        # invalid eadid should 404
        search_url = reverse('fa:singledoc-search', kwargs={'id': 'bogus-ead'})
        response = self.client.get(search_url, {'keywords': 'nothing'})
        expected, got = 404, response.status_code
        self.assertEqual(
            expected, got,
            "expected status code %s for %s with bogus eadid, got %s" %
            (expected, search_url, got))

        # simple document with no series/subseries
        search_url = reverse('fa:singledoc-search', kwargs={'id': 'leverette135'})

        response = self.client.get(search_url, {'keywords': 'photos'})
        # response should return without an error
        self.assertContains(
            response, "Search results for : <b>photos</b>",
            msg_prefix='single-document search returns normally for simple finding aid with no series')
        self.assertNotContains(
            response, "Series",
            msg_prefix='single-document search response in simple finding aid should not include series')

        response = self.client.get(search_url, {'dao': 'on'})
        self.assertContains(response, 'Photo 1',
            msg_prefix='search for digital resources in leverette should include photo 1')
        self.assertNotContains(response, 'Digitized Content',
            msg_prefix='search for digital resources should not include internal digital content')
        abbey_search_url = reverse('fa:singledoc-search', kwargs={'id': 'abbey244'})
        response = self.client.get(abbey_search_url, {'dao': 'on'})
        self.assertContains(response, 'No matches found',
            msg_prefix='document with only internal daos returns no matches for guest user')

        # when logged in as an admin, documents with internal dao should also be returned

        self.client.login(username='marbl', password='marbl')
        response = self.client.get(search_url, {'dao': 'on'})
        self.assertContains(response, 'Digitized Content',
            msg_prefix='search for digital resources should include internal digital content if user has access')
        response = self.client.get(abbey_search_url, {'dao': 'on'})
        self.assertContains(response, 'Resource available online',
            msg_prefix='document with only internal daos returns matches for user with access')


    def test_findingaid_match_count(self):
        # finding aid match_count field can only be tested via eXist return
        findingaid = FindingAid.objects.filter(highlight='mansion institute').get(eadid='raoul548')
        # get number of matched keywords in series
        self.assertEqual(3, findingaid.dsc.c[3].match_count)
        # get number of matched keywords in index
        self.assertEqual(2, findingaid.archdesc.index[0].match_count)

        # subseries links
        series = Series.objects.also('ead__eadid').filter(highlight='champmanoir').get(id='raoul548_s4')
        links = _subseries_links(series)
        self.assertPattern(".*class='exist-match'.*2 matches", links[0])  # 2 matches in series 4.1
        self.assertPattern(".*class='exist-match'.*1 match", links[1][0])  # 1 match in series 4.1a
        self.assertPattern("^((?!class='exist-match').)*$", links[-1])   # NO matches in last subseries


