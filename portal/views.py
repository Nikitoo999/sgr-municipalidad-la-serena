from django.contrib.auth.decorators import login_required
from django.shortcuts import render

DEFAULT_COLOR = "#C62828"


@login_required
def dashboard(request):
    employee = getattr(request.user, "employee", None)
    delegation = getattr(employee, "delegation", None)
    return render(request, "portal/dashboard.html", {
        "delegation_name": getattr(delegation, "name", "Administración"),
        "delegation_color": getattr(delegation, "color", "") or DEFAULT_COLOR,
        "employee": employee,
    })
