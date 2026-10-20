"""URLconf used to prove that views without a declared access policy are refused."""
from django.http import HttpResponse
from django.urls import include, path

from accounts.access import public


def forgot_policy(request):
    return HttpResponse("secret")


@public
def declared(request):
    return HttpResponse("ok")


urlpatterns = [
    path("forgot/", forgot_policy),
    path("declared/", declared),
    path("accounts/", include("accounts.urls")),
    path("", include("dashboards.urls")),
]
