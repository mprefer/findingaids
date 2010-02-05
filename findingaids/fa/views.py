from django.shortcuts import render_to_response
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from findingaids.fa.models import FindingAid

def browse(request):  
    fa = FindingAid.objects.only(['title', 'author', 'unittitle', 'abstract', 'physical_desc']).all()
    return _paginated_browse(request, fa)       

def letter_browse(request, letter):  
    fa = FindingAid.objects.filter(title__startswith=letter).order_by('title').only(['title', 'author', 'unittitle', 'abstract', 'physical_desc'])
    return _paginated_browse(request, fa)
    return render_to_response('findingaids/browse.html', { 'findingaids' : fa,
                                                           'xquery': fa.query.getQuery() })


# object pagination - adapted directly from django paginator documentation
def _paginated_browse(request, fa):
    paginator = Paginator(fa, 10)
     # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    # If page request (9999) is out of range, deliver last page of results.
    try:
        findingaids = paginator.page(page)
    except (EmptyPage, InvalidPage):
        findingaids = paginator.page(paginator.num_pages)


    return render_to_response('findingaids/browse.html', { 'findingaids' : findingaids,
                                                           'xquery': fa.query.getQuery() })
    
