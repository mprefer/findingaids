.. _CHANGELOG:

CHANGELOG
=========

The following is a summary of changes and improvements to the Finding
Aids application.  New features in each version should be listed, with the most
recent version first.  Upgrade or deployment notes should be found in
:ref:`DEPLOYNOTES`.

1.0 micro releases
------------------

1.0.12
~~~~~~

* Catch exceptions when reloading cached content feed data.

1.0.11
~~~~~~

* Adjust the XQuery for single-document searches to be more efficient
  for large documents, in order to address a time-out issue identified
  in SCLC1083.

1.0.10
~~~~~~

* Better error-handling for empty list title in EAD when prepping for
  preview/load.
* Require eulxml 0.17.1 for improved xpath parser handling.

1.0.9
~~~~~

* Now compatible with Python 2.7
* Upgrade to Django 1.3 and the latest released versions of the
  broken-out eulcore modules (:mod:`eulxml`, :mod:`eulexistdb`, and
  :mod:`eulcommon`).
* Minor error-handling and search-engine optimization for the feedback
  page.
* Rewrite rule to handle non-existent URL
  ('-Libraries-EmoryFindingAids') that search engines follow from
  other Emory sites.
* Add a reset button to the advanced search form so that a selected
  repository can be unselected.

1.0.8
~~~~~

* bugfix: allow admin publication of documents with a ``<title>`` at
  the beginning of the document ``<unittitle>``
* bugfix: Revised logic for celery PDF caching task, to ensure cache is
  cleared and reloaded with the new version of a published document.
* Plain HTML page with a list of all published findingaids, with a
  link to the full EAD xml for each, as a simple way to allow
  harvesting content.


1.0.6
~~~~~
* Newer version of :mod:`eulcore.existdb` that adds a configurable
  timeout on queries made to the eXist database.

1.0.5
~~~~~
* Fix response-time issue for series/subseries page with highlighted search
  terms.
* Rework admin site preview mode logic so site cannot get stuck in preview
  mode.
* Use pip+virtualenv to manage dependencies like eulcore.

1.0.4
~~~~~
* Fix preview subseries link so it stays in series mode
* Update to eulcore to try to improve xpath error reporting for errors that
  are being generated on the prodution site by web spiders.

1.0.3
~~~~~
Minor usability and display tweaks:
* Show all alpha-browse page labels instead of only 9
* Brief search tips on the main page

1.0.2
~~~~~
* Fix character corruption issue in origination field on main finding aid
  page.

1.0.1
~~~~~
* Correct single-doucment search for simple finding aids with no series.

1.0 Site Design & Content
-------------------------

* Users can view additional pages maintained by the finding aids administrator
  which contain helpful information for regarding searching, defining terms,
  participating institutions, etc.
* User visiting the homepage sees one of several archivist-selected images
  (rotate randomly on page refresh) to market unique items in MARBL's collections.
* A user visiting the Finding Aids home page will see the most recent archivist-
  entered/created announcement (if any), in order to receive up-to-date news
  about special events or notifications about site downtime.
* Researchers can submit feedback relating to the website site from the main
  homepage to help improve content and functionality.
* When a researcher is viewing a single finding aid, they can submit feedback to
  help correct typos and errors in the text or provide additional information
  which may be helpful to future researchers.
* Prospective visitors/researchers can submit a request for materials to
  facilitate retrieval prior to their arrival, which will be routed to the
  appropriate repository via email.
* Researchers can select a repository (other than 'All') on the advanced search
  form and submit the form without entering any other search terms, in order to
  browse all finding aids from a single repository.
* Users view html and PDF versions of finding aids that are consistently and
  cleanly formatted and displayed according to MARBL formatting requirements.

0.4.1 Unitid Identifiers
------------------------

* Custom manage command to add machine-readable identifiers to the top-level
  unitid tag.

0.4 Persistent IDs
------------------

* A system administrator can run a command that will generate ARKs for
  all existing EAD documents that do not already have ARKs to update the
  documents and store the ARK in the appropriate eadid attribute.
* When an archivist runs the 'prep' step in the Finding Aid admin
  site, an ARK will be generated and added to the 'prepared' EAD.
* When an archivist runs the 'prep' step on a Finding Aid with no ARK
  stored in the EADID, but for which an ARK has already been generated,
  the existing ARK will be used and the archivist will see an
  explanatory message.
* When an archivist attempts to publish a Finding Aid without an ARK
  stored in the EADID, the document will not be published and the
  archivist will see an explanatory message.
* A researcher or search engine accessing a Finding Aid document has
  access to view and bookmark the permanent url for that document.
* When researchers try to use the Emory Finding Aids Database and it
  is down, they will see a message about the problem and who to contact.


0.3 Enhanced Search
-------------------

* When viewing a finding aid after a search, a researcher can easily find search
  terms and exact phrases because they are highlighted.
* When viewing a finding aid after a search, a researcher sees an indicator of
  which sections of the finding aid include their search terms.
* A system administrator can run a script to migrate EAD files in the
  configured source directory from EAD DTD format to EAD XSD schema.
* When an admin cleans, publishes, or previews an schema-based EAD document,
  the application validates against the XSD schema.
* Researchers can retrieve an alphabetical browse list in less than 5 seconds,
  based on the first letter of a stakeholder specified field.
* Researchers receive their search results in less than 5 seconds.
* Researchers can see how many pages of search results there are, and jump to
  any section of search results from any page in the search results.
* When viewing a finding aid with series or sub-series, a researcher can use
  breadcrumbs to navigate within the hierarchy of the document.
* Researchers can search for an exact phrase in all indexed fields in the full
  text of the finding aid, to allow targeted discovery.
* Researchers can search using wildcards to match partial or variant words.
* Researchers can use grouping and boolean operators in the main search input,
  to generate very precise, relevant search results.
* Researchers find finding aids with matches in stake-holder specified fields
  at the top of search results.
* When viewing a finding aid, a researcher can search within that one document,
  to find relevant folder contents in a large finding aid.
* Researchers can click on a subject heading (any of the controlaccess terms)
  in a single finding aid to discover other finding aids with the same subject headings.
* When browsing finding aids by any first letter, a researcher can jump to
  alphabetical groupings within that letter, to enable identifying and accessing
  a particular portion of that browse listing (e.g., A-Ar, As-Ax, etc.).
* When viewing a finding aid found via search, a researcher can get back to the
  last page of search results they were on.
* Researchers can filter their search by repository (MARBL, Pitts, University
  Archives, etc.), to find resources available at a specific location.
* Users interact with a site that has a consistent look and feel across
  Emory Libraries websites.

**Minor changes**

* Pisa/ReportLab PDF generation has been replaced with XSL-FO and Apache FOP.
* Logging now available in runserver
* Clean urls for series/subseries/index (without redundant eadid)
* Includes a prototype version simplepages for editable site content

0.2 Data Preparation / Admin site
---------------------------------

Replaces the legacy command-line ant process for validating EAD xml
data and loading it to the eXist database.

* An authorized archivist can log in to an admin section of the
  finding aids site inaccessible to other users.
* Logged in admins can view a list of finding aid files recently
  modified on F:\ and ready for upload, sorted by last modified.
* Logged in admins can select files from the recently modified list
  for upload directly to publication.
* Logged in admins can select a file from the recently modified list
  for preparing, see a list of changes made, and optionally download
  the prepared version if changes were made, in order to safely
  prepare the canonical copy of the EAD xml files.
* Logged in admins can select files from the recently modified list
  for preview; multiple admins can preview different documents
  simultaneously.
* An admin previewing a finding aid can click a link (on any page in a
  multi-page finding aid) to publish that document.
* When an admin tries to publish or preview an invalid finding aid,
  the user sees a meaningful error message directing them how to fix
  it.
* When the web application is unable to save a finding aid, the user
  sees a meaningful message describing the problem and how to proceed.
* Logged in admins can view a minimal alphabetical list of published
  finding aids.
* Logged in admins can select a finding aid for deletion from the
  alphabetical list of published finding aids.
* When a collection is removed from the production site, patrons
  accessing their URLs are referred to MARBL staff for collection
  status.
* Researchers can receive a pdf of a finding aid in less than 10
  seconds.
* A search engine or web crawler can harvest descriptive metadata
  based on the EAD contents along with the HTML data, to improve
  google-ability.
* A system administrator can run a command to prepare all or specified
  EAD xml files in the configured directory, in order to easily update
  all existing files to new standards.
* A system administrator can run a command to load all or specified
  EAD xml files in the configured source directory to the configured
  eXist collection, in order to easily populate a new eXist collection


0.1 Port to Django
------------------

Reimplementation of the functionality of the existing PHP Finding Aids
site in django and eXist 1.4.

* Researchers can browse finding aids alphabetically by first letter
  of title.
* Researchers can click on the title of a finding aid in search or
  browse results to view more details about what resources are
  available in that collection.
* Researchers can search finding aids by keyword.
* Developers can access EAD XML objects in an eXist-backed Django
  Model workalike.
* Researchers can click 'download PDF' when viewing a single finding
  aid to download a PDF version of the entire finding aid.
* Researchers can navigate through finding aid site with the same look
  and feel of the library site.
* When a researcher clicks on an old link to a drupal or pre-drupal
  finding aid URL, they are automatically redirected to new finding
  aid URLs.