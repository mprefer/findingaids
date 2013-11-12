# file findingaids/fa/tests/models.py
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

from django.test import TestCase as DjangoTestCase

from eulxml.xmlmap import load_xmlobject_from_file, load_xmlobject_from_string
from eulexistdb.testutil import TestCase

from findingaids.fa.models import FindingAid, LocalComponent, EadRepository
from findingaids.fa.utils import pages_to_show, ead_lastmodified, \
    collection_lastmodified


## unit tests for model objects in findingaids.fa

exist_fixture_path = path.join(path.dirname(path.abspath(__file__)), 'fixtures')
exist_index_path = path.join(path.dirname(path.abspath(__file__)), '..', '..', 'exist_index.xconf')


class FindingAidTestCase(DjangoTestCase):
    # test finding aid model (customization of eulcore xmlmap ead object)
    FIXTURES = ['leverette135.xml',  # simple finding aid (no series/subseries), origination is a person name
                'abbey244.xml',      # finding aid with series (no subseries), origination is a corporate name
                'raoul548.xml',      # finding aid with series & subseries, origination is a family name
                'bailey807.xml',     # finding aid with series, no origination
                'adams465.xml'
                ]

    def setUp(self):
        self.findingaid = dict()
        for file in self.FIXTURES:
            filebase = file.split('.')[0]
            self.findingaid[filebase] = load_xmlobject_from_file(path.join(exist_fixture_path,
                                  file), FindingAid)

    def test_init(self):
        for file, fa in self.findingaid.iteritems():
            self.assert_(isinstance(fa, FindingAid))

    def test_custom_fields(self):
        # list title variants
        # NOTE: list_title is now a NodeField; calling __unicode__ explicitly to do a string compare
        #  - origination, person name
        self.assertEqual("Leverette, Fannie Lee.", self.findingaid['leverette135'].list_title.__unicode__())
        self.assertEqual("L", self.findingaid['leverette135'].first_letter)
        #  - origination, corporate name
        self.assertEqual("Abbey Theatre.", self.findingaid['abbey244'].list_title.__unicode__())
        self.assertEqual("A", self.findingaid['abbey244'].first_letter)
        #  - origination, family name
        self.assertEqual("Raoul family.", self.findingaid['raoul548'].list_title.__unicode__())
        self.assertEqual("R", self.findingaid['raoul548'].first_letter)
        #  - no origination - list title falls back to unit title
        self.assertEqual("Bailey and Thurman families papers, circa 1882-1995",
                         self.findingaid['bailey807'].list_title.__unicode__())
        self.assertEqual("B", self.findingaid['bailey807'].first_letter)

        # dc_subjects
        self.assert_(u'Irish drama--20th century.' in self.findingaid['abbey244'].dc_subjects)
        self.assert_(u'Theater--Ireland--20th century.' in self.findingaid['abbey244'].dc_subjects)
        self.assert_(u'Dublin (Ireland)' in self.findingaid['abbey244'].dc_subjects)
        # dc_contributors
        self.assert_(u'Bailey, I. G. (Issac George), 1847-1914.' in self.findingaid['bailey807'].dc_contributors)
        self.assert_(u'Bailey, Susie E., d. 1948.' in self.findingaid['bailey807'].dc_contributors)
        self.assert_(u'Thurman, Howard, 1900-1981.' in self.findingaid['bailey807'].dc_contributors)
        self.assert_(u'Thurman, Sue Bailey.' in self.findingaid['bailey807'].dc_contributors)

    def test_series_info(self):
        info = self.findingaid['raoul548'].dsc.c[0].series_info()
        self.assert_(isinstance(info, ListType))
        self.assertEqual("Scope and Content Note", unicode(info[0].head))
        self.assertEqual("Arrangement Note", unicode(info[1].head))

        # series info problem when scopecontent is missing a <head>; contains use restriction
        info = self.findingaid['raoul548'].dsc.c[-1].c[-1].series_info()
        self.assert_(isinstance(info, ListType))
        self.assert_("contains all materials related to " in
            info[0].content[0].__unicode__())  # scopecontent with no head
        self.assertEqual("Arrangement Note", unicode(info[1].head))
        self.assertEqual("Terms Governing Use and Reproduction", unicode(info[2].head))
        self.assertEqual("Restrictions on Access", unicode(info[3].head))

    def test_series_displaylabel(self):
        self.assertEqual("Series 1: Letters and personal papers, 1865-1982",
                self.findingaid['raoul548'].dsc.c[0].display_label())
        # no unitid
        self.assertEqual("Financial and legal papers, 1890-1970",
                self.findingaid['raoul548'].dsc.c[2].display_label())

    def test_dc_fields(self):
        fields = self.findingaid['abbey244'].dc_fields()

        self.assert_("Abbey Theatre collection, 1921-1995" in [title.__unicode__() for title in fields["title"]])
        self.assert_("Abbey Theatre." in fields["creator"])
        self.assert_("Emory University" in fields["publisher"])
        self.assert_("2002-02-24" in fields["date"])
        self.assert_("eng" in fields["language"])
        self.assert_("Irish drama--20th century." in fields["subject"])
        self.assert_("Theater--Ireland--20th century." in fields["subject"])
        self.assert_("Dublin (Ireland)" in fields["subject"])
        self.assert_("http://pidtest.library.emory.edu/ark:/25593/1fx" in fields["identifier"])

        fields = self.findingaid['bailey807'].dc_fields()
        self.assert_("Bailey, I. G. (Issac George), 1847-1914." in fields["contributor"])
        self.assert_("Bailey, Susie E., d. 1948." in fields["contributor"])
        self.assert_("Thurman, Howard, 1900-1981." in fields["contributor"])
        self.assert_("Thurman, Sue Bailey." in fields["contributor"])

    def test_local_component(self):
        # local component with custom property - first_file_item
        self.assert_(isinstance(self.findingaid['abbey244'].dsc.c[0], LocalComponent))
        self.assert_(isinstance(self.findingaid['abbey244'].dsc.c[0].c[0], LocalComponent))
        # abbey244 series 1 - no section headings, first c should be first file
        self.assertTrue(self.findingaid['abbey244'].dsc.c[0].c[0].first_file_item)
        self.assertFalse(self.findingaid['abbey244'].dsc.c[0].c[1].first_file_item)
        self.assertFalse(self.findingaid['abbey244'].dsc.c[0].c[-1].first_file_item)
        # raoul548 series 1.1 - first item is a section, second item should be first file
        self.assertFalse(self.findingaid['raoul548'].dsc.c[0].c[0].c[0].first_file_item)
        self.assertTrue(self.findingaid['raoul548'].dsc.c[0].c[0].c[1].first_file_item)


class EadRepositoryTestCase(TestCase):
    exist_fixtures = {'files': [path.join(exist_fixture_path, 'pomerantz890.xml')] }

    def test_distinct(self):
        repos = EadRepository.distinct()
        # should be a distinct, space-normalized list of subareas
        self.assert_('Pitts Theology Library' in repos)
        self.assert_('Manuscript, Archives, and Rare Book Library' in repos)



