from django.db import models
from Account.models import Account


class Author(models.Model):
    AuthorID = models.AutoField(primary_key=True)
    FirstName = models.CharField(max_length=100)
    LastName = models.CharField(max_length=100)


class Genre(models.Model):
    GenreID = models.AutoField(primary_key=True)
    Name = models.CharField(max_length=100, unique=True)


class Book(models.Model):
    BookID = models.AutoField(primary_key=True)
    ISBN = models.CharField(max_length=13, unique=True)
    Author = models.ForeignKey(Author, on_delete=models.CASCADE, db_column='AuthorID')
    Genre = models.ForeignKey(Genre, on_delete=models.PROTECT, db_column='GenreID')
    Title = models.CharField(max_length=255)
    PublicationDate = models.DateField(null=True, blank=True)
    CoverImageURL = models.URLField(max_length=500, null=True, blank=True)


class BookCopy(models.Model):
    CopyID = models.AutoField(primary_key=True)
    Book = models.ForeignKey(Book, on_delete=models.CASCADE, db_column='BookID')
    Status = models.CharField(max_length=20, default='Available')


class Rental(models.Model):
    RentalID = models.AutoField(primary_key=True)
    Copy = models.ForeignKey(BookCopy, on_delete=models.CASCADE, db_column='CopyID')
    User = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='rentals', db_column='UserID')
    ProcessedByUser = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='processed_rentals', db_column='ProcessedByUserID')
    RentTime = models.DateTimeField(auto_now_add=True)
    DueDate = models.DateTimeField()


class Return(models.Model):
    ReturnID = models.AutoField(primary_key=True)
    Rental = models.ForeignKey(Rental, on_delete=models.CASCADE, db_column='RentalID')
    ProcessedByUser = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='processed_returns', db_column='ProcessedByUserID')
    ReturnTime = models.DateTimeField(auto_now_add=True)


class Reservation(models.Model):
    ReservationID = models.AutoField(primary_key=True)
    User = models.ForeignKey(Account, on_delete=models.CASCADE, db_column='UserID')
    Book = models.ForeignKey(Book, on_delete=models.CASCADE, db_column='BookID')
    ReservationTime = models.DateTimeField(auto_now_add=True)
    ExpiryTime = models.DateTimeField()
    Status = models.CharField(max_length=20, default='Active')