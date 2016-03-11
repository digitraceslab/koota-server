from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse, reverse_lazy
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django.template.response import TemplateResponse

from . import models
from . import devices
from . import util
from . import views


class JoinGroupForm(forms.Form):
    invite_code = forms.CharField()
    groups = forms.CharField(widget=forms.HiddenInput, required=False)
@login_required
def group_join(request):
    """View to present group invitations.

    This will:
    - Allow user to specify an invite code.
    - Confirm the groups that the user will join
    - Add user to those groups.
    """
    context = c = { }
    user = request.user
    if not user.is_authenticated():
        raise Http404 # should never get here, we have login_required
    if request.method == 'POST':
        form = JoinGroupForm(request.POST)
        if form.is_valid():
            invite_code = form.cleaned_data['invite_code']
            groups = models.Group.objects.filter(invite_code=invite_code)
            context['groups'] = groups
            groups_str = ','.join(sorted(g.name for g in groups))
            if groups_str == form.cleaned_data['groups']:
                # Second stage.  User was presented the groups on the
                # last round, so now do the actual addition.
                c['round'] = 'done'
                for group in groups:
                    #group.subjects.add(request.user)
                    if group.subjects.filter(id=user.id).exists():
                        continue
                    models.GroupSubject.objects.create(user=user, group=group)
                    print("added %s to %s"%(user, group))
            else:
                # First stage.  User entered invite code.  We have to
                # present the data again, so that user can verify the
                # group that they are joining.
                c['round'] = 'verify'
                form.data = form.data.copy()
                form.data['groups'] = groups_str
    else:
        # Initial, present box for invite code.
        c['round'] = 'initial'
        form = JoinGroupForm(initial=request.GET)
    c['form'] = form
    return TemplateResponse(request, 'koota/group_join.html',
                            context=context)

class GroupView(DetailView):
    pass


class BaseGroup(object):
    pass
