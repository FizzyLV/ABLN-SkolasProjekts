from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('reserve/<int:book_id>/', views.reserve_book, name='reserve_book'),
    path('cancel-reservation/<int:reservation_id>/', views.cancel_reservation, name='cancel_reservation'),
    
    # Admin book management
    path('add-book/', views.add_book, name='add_book'),
    path('edit-book/<int:book_id>/', views.edit_book, name='edit_book'),
    path('delete-book/<int:book_id>/', views.delete_book, name='delete_book'),
    path('add-copies/<int:book_id>/', views.add_copies, name='add_copies'),
    path('edit-copy/<int:copy_id>/', views.edit_copy, name='edit_copy'),
    
    # Admin author and genre management
    path('manage-authors/', views.manage_authors, name='manage_authors'),
    path('manage-genres/', views.manage_genres, name='manage_genres'),
    
    path('reservations/', views.reservations, name='reservations'),
    
    path('issue-book/<int:reservation_id>/', views.issue_book, name='issue_book'),
    path('process-return/<int:rental_id>/', views.process_return, name='process_return'),
    path('delete-reservation/<int:reservation_id>/', views.delete_reservation, name='delete_reservation'),
    path('update-reservation-dates/<int:reservation_id>/', views.update_reservation_dates, name='update_reservation_dates'),
    path('overdue/', views.overdue, name='overdue'),
]