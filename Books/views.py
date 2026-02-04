from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count, Case, When, IntegerField, Prefetch
from django.utils import timezone
from django.db import transaction
from datetime import timedelta, datetime
from Books.models import Book, BookCopy, Author, Genre, Reservation, Rental, Return
from Account.decorators import login_required, admin_required


@login_required
def home(request):
    """Display books with search and filter functionality"""
    user_id = request.session.get('user_id')
    from Account.models import Account
    
    try:
        account = Account.objects.select_related('Role').get(UserID=user_id)
        is_admin = account.Role.RoleID == 2 if account.Role else False
    except Account.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    # Get search and filter parameters
    search_query = request.GET.get('search', '').strip()
    genre_filter = request.GET.get('genre', '')
    author_filter = request.GET.get('author', '')
    availability_filter = request.GET.get('availability', '')
    
    # Start with all books - use select_related to avoid N+1 queries
    books = Book.objects.select_related('Author', 'Genre').annotate(
        total_copies=Count('bookcopy'),
        available_copies=Count(
            Case(
                When(bookcopy__Status='Available', then=1),
                output_field=IntegerField()
            )
        )
    )
    
    # Apply search filter
    if search_query:
        books = books.filter(
            Q(Title__icontains=search_query) |
            Q(Author__FirstName__icontains=search_query) |
            Q(Author__LastName__icontains=search_query) |
            Q(ISBN__icontains=search_query) |
            Q(Genre__Name__icontains=search_query)
        )
    
    # Apply author filter
    if author_filter:
        books = books.filter(Author__AuthorID=author_filter)
    
    # Apply genre filter
    if genre_filter:
        books = books.filter(Genre__GenreID=genre_filter)
    
    # Apply availability filter
    if availability_filter == 'available':
        books = books.filter(available_copies__gt=0)
    elif availability_filter == 'unavailable':
        books = books.filter(available_copies=0)
    
    # Get all authors and genres for filter dropdowns (only load what we need)
    all_authors = Author.objects.only('AuthorID', 'FirstName', 'LastName').order_by('LastName', 'FirstName')
    genres = Genre.objects.only('GenreID', 'Name').order_by('Name')
    
    # Check user's active reservations and get their status
    user_reservations = []
    user_reservation_data = {}
    if not is_admin:
        # Get user's active reservations
        user_reservations_qs = Reservation.objects.filter(
            User=account,
            Status='Active'
        ).select_related('Book')
        
        user_reservations = [r.Book_id for r in user_reservations_qs]
        
        # Get all rentals for this user in one query
        user_book_ids = [r.Book_id for r in user_reservations_qs]
        if user_book_ids:
            user_rentals = Rental.objects.filter(
                User=account,
                Copy__Book_id__in=user_book_ids
            ).select_related('Copy', 'Copy__Book').prefetch_related(
                Prefetch(
                    'return_set',
                    queryset=Return.objects.all()
                )
            )
            
            # Build a lookup map: book_id -> list of rentals
            rentals_by_book = {}
            for rental in user_rentals:
                book_id = rental.Copy.Book_id
                if book_id not in rentals_by_book:
                    rentals_by_book[book_id] = []
                rentals_by_book[book_id].append(rental)
        else:
            rentals_by_book = {}
        
        # Get detailed reservation data for the user
        for reservation in user_reservations_qs:
            # Find if this reservation has a rental
            rental = None
            book_rentals = rentals_by_book.get(reservation.Book_id, [])
            for r in book_rentals:
                if r.RentTime >= reservation.ReservationTime:
                    rental = r
                    break
            
            return_record = None
            if rental:
                # Already prefetched
                return_records = list(rental.return_set.all())
                return_record = return_records[0] if return_records else None
            
            # Determine phase
            if return_record:
                phase = 'Returned'
            elif rental:
                phase = 'Rented'
            else:
                phase = 'Reserved'
            
            user_reservation_data[reservation.Book.BookID] = {
                'reservation': reservation,
                'phase': phase,
                'rental': rental,
                'return_record': return_record,
            }
    
    context = {
        'books': books,
        'all_authors': all_authors,
        'genres': genres,
        'is_admin': is_admin,
        'search_query': search_query,
        'author_filter': author_filter,
        'genre_filter': genre_filter,
        'availability_filter': availability_filter,
        'user_reservations': user_reservations,
        'user_reservation_data': user_reservation_data,
    }
    
    return render(request, 'home.html', context)


@login_required
@transaction.atomic
def reserve_book(request, book_id):
    """Handle book reservation for users"""
    user_id = request.session.get('user_id')
    from Account.models import Account
    
    try:
        account = Account.objects.get(UserID=user_id)
    except Account.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    book = get_object_or_404(Book, BookID=book_id)
    
    # Use select_for_update to lock the row and prevent race conditions
    # This ensures only one user can reserve a specific copy at a time
    available_copy = BookCopy.objects.select_for_update().filter(
        Book=book, 
        Status='Available'
    ).first()
    
    if not available_copy:
        messages.error(request, 'This book is not available for reservation.')
        return redirect('home')
    
    # Check if user already has an ACTIVE reservation for this book
    # (Completed or Cancelled reservations should not block new reservations)
    existing_reservation = Reservation.objects.filter(
        User=account,
        Book=book,
        Status='Active'  # Only check for Active reservations
    ).exists()  # Use exists() instead of first() for better performance
    
    if existing_reservation:
        messages.warning(request, 'You already have an active reservation for this book.')
        return redirect('home')
    
    # Create reservation with 7-day expiry
    expiry_time = timezone.now() + timedelta(days=7)
    
    Reservation.objects.create(
        User=account,
        Book=book,
        ExpiryTime=expiry_time,
        Status='Active'
    )
    
    # Mark the copy as Reserved (within the same transaction)
    available_copy.Status = 'Reserved'
    available_copy.save()
    
    messages.success(request, f'Successfully reserved "{book.Title}"!')
    return redirect('home')


@login_required
@transaction.atomic
def cancel_reservation(request, reservation_id):
    """Cancel a reservation"""
    user_id = request.session.get('user_id')
    from Account.models import Account
    
    try:
        account = Account.objects.get(UserID=user_id)
    except Account.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    reservation = get_object_or_404(Reservation, ReservationID=reservation_id, User=account)
    
    # Use select_for_update to prevent race conditions
    reserved_copy = BookCopy.objects.select_for_update().filter(
        Book=reservation.Book, 
        Status='Reserved'
    ).first()
    
    if reserved_copy:
        reserved_copy.Status = 'Available'
        reserved_copy.save()
    
    reservation.Status = 'Cancelled'
    reservation.save()
    
    messages.success(request, 'Reservation cancelled successfully.')
    return redirect('home')


@admin_required
def add_book(request):
    """Admin page to add a new book"""
    if request.method == 'POST':
        # Handle form submission
        title = request.POST.get('title', '').strip()
        isbn = request.POST.get('isbn', '').strip()
        author_id = request.POST.get('author')
        genre_id = request.POST.get('genre')
        publication_date = request.POST.get('publication_date')
        cover_url = request.POST.get('cover_url', '').strip()
        num_copies = request.POST.get('num_copies', '1')
        
        errors = {}
        
        if not title:
            errors['title'] = 'Title is required.'
        if not isbn:
            errors['isbn'] = 'ISBN is required.'
        elif Book.objects.filter(ISBN=isbn).exists():
            errors['isbn'] = 'A book with this ISBN already exists.'
        if not author_id:
            errors['author'] = 'Author is required.'
        if not genre_id:
            errors['genre'] = 'Genre is required.'
        
        try:
            num_copies = int(num_copies)
            if num_copies < 1:
                errors['num_copies'] = 'Number of copies must be at least 1.'
            elif num_copies > 100:  # Add reasonable upper limit
                errors['num_copies'] = 'Number of copies cannot exceed 100.'
        except ValueError:
            errors['num_copies'] = 'Invalid number of copies.'
        
        if not errors:
            try:
                # Use atomic transaction to ensure book and copies are created together
                with transaction.atomic():
                    # Create the book
                    book = Book.objects.create(
                        Title=title,
                        ISBN=isbn,
                        Author_id=author_id,
                        Genre_id=genre_id,
                        PublicationDate=publication_date if publication_date else None,
                        CoverImageURL=cover_url if cover_url else None
                    )
                    
                    # Create book copies - use bulk_create for better performance
                    copies = [BookCopy(Book=book, Status='Available') for _ in range(num_copies)]
                    BookCopy.objects.bulk_create(copies)
                
                messages.success(request, f'Successfully added "{title}" with {num_copies} cop{"y" if num_copies == 1 else "ies"}!')
                return redirect('home')
            except Exception as e:
                errors['general'] = f'An error occurred: {str(e)}'
    
    # Get authors and genres for dropdowns (only load what we need)
    authors = Author.objects.only('AuthorID', 'FirstName', 'LastName').order_by('LastName', 'FirstName')
    genres = Genre.objects.only('GenreID', 'Name').order_by('Name')
    
    context = {
        'authors': authors,
        'genres': genres,
        'errors': locals().get('errors', {}),
        'data': request.POST if request.method == 'POST' else {}
    }
    
    return render(request, 'add_book.html', context)


@admin_required
def edit_book(request, book_id):
    """Admin page to edit a book"""
    book = get_object_or_404(Book.objects.select_related('Author', 'Genre'), BookID=book_id)
    
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        isbn = request.POST.get('isbn', '').strip()
        author_id = request.POST.get('author')
        genre_id = request.POST.get('genre')
        publication_date = request.POST.get('publication_date')
        cover_url = request.POST.get('cover_url', '').strip()
        
        errors = {}
        
        if not title:
            errors['title'] = 'Title is required.'
        if not isbn:
            errors['isbn'] = 'ISBN is required.'
        elif Book.objects.filter(ISBN=isbn).exclude(BookID=book_id).exists():
            errors['isbn'] = 'A book with this ISBN already exists.'
        if not author_id:
            errors['author'] = 'Author is required.'
        if not genre_id:
            errors['genre'] = 'Genre is required.'
        
        if not errors:
            try:
                book.Title = title
                book.ISBN = isbn
                book.Author_id = author_id
                book.Genre_id = genre_id
                book.PublicationDate = publication_date if publication_date else None
                book.CoverImageURL = cover_url if cover_url else None
                book.save()
                
                messages.success(request, f'Successfully updated "{title}"!')
                return redirect('home')
            except Exception as e:
                errors['general'] = f'An error occurred: {str(e)}'
    
    authors = Author.objects.only('AuthorID', 'FirstName', 'LastName').order_by('LastName', 'FirstName')
    genres = Genre.objects.only('GenreID', 'Name').order_by('Name')
    
    # Calculate copy statistics - use aggregate for better performance
    copy_stats = book.bookcopy_set.aggregate(
        total=Count('CopyID'),
        available=Count(Case(When(Status='Available', then=1), output_field=IntegerField())),
        reserved=Count(Case(When(Status='Reserved', then=1), output_field=IntegerField())),
        rented=Count(Case(When(Status='Rented', then=1), output_field=IntegerField())),
        damaged=Count(Case(When(Status='Damaged', then=1), output_field=IntegerField())),
        lost=Count(Case(When(Status='Lost', then=1), output_field=IntegerField())),
    )
    
    context = {
        'book': book,
        'authors': authors,
        'genres': genres,
        'errors': locals().get('errors', {}),
        'total_copies': copy_stats['total'],
        'available_copies': copy_stats['available'],
        'reserved_copies': copy_stats['reserved'],
        'rented_copies': copy_stats['rented'],
        'damaged_copies': copy_stats['damaged'],
        'lost_copies': copy_stats['lost'],
    }
    
    return render(request, 'edit_book.html', context)


@admin_required
@transaction.atomic
def delete_book(request, book_id):
    """Admin endpoint to delete a book"""
    book = get_object_or_404(Book, BookID=book_id)
    book_title = book.Title
    
    try:
        book.delete()
        messages.success(request, f'Successfully deleted "{book_title}".')
    except Exception as e:
        messages.error(request, f'Could not delete book: {str(e)}')
    
    return redirect('home')


@admin_required
@transaction.atomic
def add_copies(request, book_id):
    """Admin endpoint to add more copies of a book and renumber all copies"""
    book = get_object_or_404(Book, BookID=book_id)
    
    if request.method == 'POST':
        try:
            num_copies = int(request.POST.get('num_copies', 1))
            if num_copies < 1 or num_copies > 10:
                messages.error(request, 'Number of copies must be between 1 and 10.')
                return redirect('edit_book', book_id=book_id)
            
            # Get all existing copies with their current state
            existing_copies = list(BookCopy.objects.filter(Book=book).order_by('CopyID'))
            copy_data = [{'status': copy.Status} for copy in existing_copies]
            
            # Add data for new copies
            copy_data.extend([{'status': 'Available'} for _ in range(num_copies)])
            
            # Delete all existing copies
            BookCopy.objects.filter(Book=book).delete()
            
            # Recreate all copies in order - use bulk_create for performance
            new_copies = [BookCopy(Book=book, Status=data['status']) for data in copy_data]
            BookCopy.objects.bulk_create(new_copies)
            
            messages.success(request, f'Successfully added {num_copies} cop{"y" if num_copies == 1 else "ies"} of "{book.Title}" and renumbered all copies.')
        except ValueError:
            messages.error(request, 'Invalid number of copies.')
        except Exception as e:
            messages.error(request, f'Error adding copies: {str(e)}')
    
    return redirect('edit_book', book_id=book_id)


@admin_required
@transaction.atomic
def edit_copy(request, copy_id):
    """Admin endpoint to update a book copy's status"""
    copy = get_object_or_404(BookCopy, CopyID=copy_id)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        # Only allow Available, Damaged, and Lost statuses
        # Reserved and Rented are managed through reservations and rentals
        if new_status in ['Available', 'Damaged', 'Lost']:
            copy.Status = new_status
            copy.save()
            messages.success(request, f'Copy status updated to "{new_status}".')
        else:
            messages.error(request, 'Invalid status.')
    
    return redirect('home')


@admin_required
def manage_authors(request):
    """Admin page to manage authors"""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            
            if first_name and last_name:
                Author.objects.create(FirstName=first_name, LastName=last_name)
                messages.success(request, f'Successfully added author "{first_name} {last_name}".')
            else:
                messages.error(request, 'Both first name and last name are required.')
        
        elif action == 'edit':
            author_id = request.POST.get('author_id')
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            
            if author_id and first_name and last_name:
                try:
                    author = Author.objects.get(AuthorID=author_id)
                    author.FirstName = first_name
                    author.LastName = last_name
                    author.save()
                    messages.success(request, f'Successfully updated author to "{first_name} {last_name}".')
                except Author.DoesNotExist:
                    messages.error(request, 'Author not found.')
            else:
                messages.error(request, 'All fields are required.')
        
        elif action == 'delete':
            author_id = request.POST.get('author_id')
            if author_id:
                try:
                    author = Author.objects.get(AuthorID=author_id)
                    author_name = f"{author.FirstName} {author.LastName}"
                    author.delete()
                    messages.success(request, f'Successfully deleted author "{author_name}".')
                except Author.DoesNotExist:
                    messages.error(request, 'Author not found.')
                except Exception as e:
                    messages.error(request, f'Cannot delete author: {str(e)}')
        
        return redirect('manage_authors')
    
    authors = Author.objects.all().order_by('LastName', 'FirstName')
    context = {'authors': authors}
    return render(request, 'manage_authors.html', context)


@admin_required
def manage_genres(request):
    """Admin page to manage genres"""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            name = request.POST.get('name', '').strip()
            
            if name:
                if Genre.objects.filter(Name__iexact=name).exists():
                    messages.error(request, f'Genre "{name}" already exists.')
                else:
                    Genre.objects.create(Name=name)
                    messages.success(request, f'Successfully added genre "{name}".')
            else:
                messages.error(request, 'Genre name is required.')
        
        elif action == 'edit':
            genre_id = request.POST.get('genre_id')
            name = request.POST.get('name', '').strip()
            
            if genre_id and name:
                try:
                    genre = Genre.objects.get(GenreID=genre_id)
                    if Genre.objects.filter(Name__iexact=name).exclude(GenreID=genre_id).exists():
                        messages.error(request, f'Genre "{name}" already exists.')
                    else:
                        genre.Name = name
                        genre.save()
                        messages.success(request, f'Successfully updated genre to "{name}".')
                except Genre.DoesNotExist:
                    messages.error(request, 'Genre not found.')
            else:
                messages.error(request, 'Genre name is required.')
        
        elif action == 'delete':
            genre_id = request.POST.get('genre_id')
            if genre_id:
                try:
                    genre = Genre.objects.get(GenreID=genre_id)
                    genre_name = genre.Name
                    genre.delete()
                    messages.success(request, f'Successfully deleted genre "{genre_name}".')
                except Genre.DoesNotExist:
                    messages.error(request, 'Genre not found.')
                except Exception as e:
                    messages.error(request, f'Cannot delete genre: {str(e)}')
        
        return redirect('manage_genres')
    
    genres = Genre.objects.all().order_by('Name')
    context = {'genres': genres}
    return render(request, 'manage_genres.html', context)


@login_required
def reservations(request):
    """Unified page for viewing reservations - shows user's own or all (admin)"""
    user_id = request.session.get('user_id')
    from Account.models import Account
    
    try:
        account = Account.objects.select_related('Role').get(UserID=user_id)
        is_admin = account.Role.RoleID == 2 if account.Role else False
    except Account.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    # Get search and filter parameters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    phase_filter = request.GET.get('phase', '')
    sort_by = request.GET.get('sort', '-reservation_time')  # Default sort by newest first
    
    # Start with reservations query
    if is_admin:
        # Admin sees all reservations
        reservations = Reservation.objects.select_related(
            'User', 'Book', 'Book__Author', 'Book__Genre'
        )
        
        # Apply search filter
        if search_query:
            reservations = reservations.filter(
                Q(Book__Title__icontains=search_query) |
                Q(User__FirstName__icontains=search_query) |
                Q(User__LastName__icontains=search_query) |
                Q(User__Email__icontains=search_query)
            )
        
        # Apply status filter (for admins - Active/Cancelled)
        if status_filter:
            reservations = reservations.filter(Status=status_filter)
    else:
        # User sees only their own reservations
        reservations = Reservation.objects.filter(
            User=account
        ).select_related('Book', 'Book__Author', 'Book__Genre')
        
        # Apply search filter for users
        if search_query:
            reservations = reservations.filter(
                Q(Book__Title__icontains=search_query) |
                Q(Book__Author__FirstName__icontains=search_query) |
                Q(Book__Author__LastName__icontains=search_query)
            )
        
        # Apply status filter for users (Active/Cancelled/Completed)
        if status_filter:
            reservations = reservations.filter(Status=status_filter)
    
    # Apply sorting (before building phase data)
    if sort_by == 'title':
        reservations = reservations.order_by('Book__Title')
    elif sort_by == '-title':
        reservations = reservations.order_by('-Book__Title')
    elif sort_by == 'reservation_time':
        reservations = reservations.order_by('ReservationTime')
    elif sort_by == '-reservation_time':
        reservations = reservations.order_by('-ReservationTime')
    elif sort_by == 'expiry_time':
        reservations = reservations.order_by('ExpiryTime')
    elif sort_by == '-expiry_time':
        reservations = reservations.order_by('-ExpiryTime')
    else:
        reservations = reservations.order_by('-ReservationTime')
    
    # Fetch all the reservations into a list first
    reservations_list = list(reservations)
    
    # Collect all the user IDs and book IDs from the reservations
    user_ids = set()
    book_ids = set()
    for res in reservations_list:
        user_ids.add(res.User_id)
        book_ids.add(res.Book_id)
    
    # Fetch all rentals for these users and books in one query
    if user_ids and book_ids:
        all_rentals = Rental.objects.filter(
            User_id__in=user_ids,
            Copy__Book_id__in=book_ids
        ).select_related('Copy', 'Copy__Book').prefetch_related(
            Prefetch(
                'return_set',
                queryset=Return.objects.all()
            )
        )
        
        # Build a lookup: (user_id, book_id) -> list of rentals
        rentals_lookup = {}
        for rental in all_rentals:
            key = (rental.User_id, rental.Copy.Book_id)
            if key not in rentals_lookup:
                rentals_lookup[key] = []
            rentals_lookup[key].append(rental)
    else:
        rentals_lookup = {}
    
    # Build reservation data with phase information
    reservation_data = []
    now = timezone.now()
    
    for reservation in reservations_list:
        # Find if this reservation has a rental (from our lookup - no query!)
        rental = None
        key = (reservation.User_id, reservation.Book_id)
        candidate_rentals = rentals_lookup.get(key, [])
        for r in candidate_rentals:
            if r.RentTime >= reservation.ReservationTime:
                rental = r
                break
        
        return_record = None
        if rental:
            # Already prefetched - no query!
            return_records = list(rental.return_set.all())
            return_record = return_records[0] if return_records else None
        
        # Determine phase
        if reservation.Status == 'Cancelled':
            phase = 'Cancelled'
        elif return_record:
            phase = 'Returned'
        elif rental:
            phase = 'Rented'
        else:
            phase = 'Reserved'
        
        reservation_data.append({
            'reservation': reservation,
            'rental': rental,
            'return_record': return_record,
            'phase': phase,
            'is_overdue': rental and not return_record and now > rental.DueDate if rental else False,
            'is_expired': reservation.Status == 'Active' and now > reservation.ExpiryTime,
        })
    
    # Apply phase filter (after building phase data)
    if phase_filter:
        reservation_data = [item for item in reservation_data if item['phase'] == phase_filter]
    
    # Apply due date sorting if requested (only for items with rentals)
    if sort_by == 'due_date':
        reservation_data.sort(key=lambda x: x['rental'].DueDate if x['rental'] else now + timedelta(days=365))
    elif sort_by == '-due_date':
        reservation_data.sort(key=lambda x: x['rental'].DueDate if x['rental'] else now - timedelta(days=365), reverse=True)
    
    context = {
        'reservation_data': reservation_data,
        'is_admin': is_admin,
        'search_query': search_query,
        'status_filter': status_filter,
        'phase_filter': phase_filter,
        'sort_by': sort_by,
    }
    
    return render(request, 'reservations.html', context)


@admin_required
@transaction.atomic
def issue_book(request, reservation_id):
    """Admin action to issue a book (move from Reserved to Rented phase)"""
    from Account.models import Account
    
    user_id = request.session.get('user_id')
    admin = get_object_or_404(Account, UserID=user_id)
    
    reservation = get_object_or_404(Reservation.objects.select_related('User', 'Book'), ReservationID=reservation_id)
    
    if reservation.Status != 'Active':
        messages.error(request, 'This reservation is not active.')
        return redirect('reservations')
    
    # Check if already rented - use exists() for better performance
    existing_rental = Rental.objects.filter(
        User=reservation.User,
        Copy__Book=reservation.Book
    ).exclude(
        return__isnull=False
    ).exists()
    
    if existing_rental:
        messages.warning(request, 'This book has already been issued.')
        return redirect('reservations')
    
    # Find a reserved copy for this book - use select_for_update to prevent race conditions
    reserved_copy = BookCopy.objects.select_for_update().filter(
        Book=reservation.Book,
        Status='Reserved'
    ).first()
    
    if not reserved_copy:
        messages.error(request, 'No reserved copy available for this book.')
        return redirect('reservations')
        
    if request.method == 'POST':
        due_date_str = request.POST.get('due_date')
        
        if not due_date_str:
            messages.error(request, 'Due date is required.')
            return redirect('reservations')
        
        try:
            # Parse the due date
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
            due_date = timezone.make_aware(due_date.replace(hour=23, minute=59, second=59))
            
            # Validate due date is in the future
            if due_date <= timezone.now():
                messages.error(request, 'Due date must be in the future.')
                return redirect('reservations')
            
            # Create rental
            Rental.objects.create(
                Copy=reserved_copy,
                User=reservation.User,
                ProcessedByUser=admin,
                DueDate=due_date
            )
            
            # Update copy status
            reserved_copy.Status = 'Rented'
            reserved_copy.save()
            
            messages.success(request, f'Successfully issued "{reservation.Book.Title}" to {reservation.User.FirstName} {reservation.User.LastName}.')
            return redirect('reservations')
        except ValueError:
            messages.error(request, 'Invalid date format.')
            return redirect('reservations')
        except Exception as e:
            messages.error(request, f'Error issuing book: {str(e)}')
            return redirect('reservations')
    
    context = {
        'reservation': reservation,
        'reserved_copy': reserved_copy,
        'today': timezone.now(),
    }
    
    return render(request, 'issue_book.html', context)


@admin_required
@transaction.atomic
def process_return(request, rental_id):
    """Admin action to process a book return"""
    from Account.models import Account
    
    user_id = request.session.get('user_id')
    admin = get_object_or_404(Account, UserID=user_id)
    
    rental = get_object_or_404(Rental.objects.select_related('Copy', 'Copy__Book', 'User'), RentalID=rental_id)
    
    # Check if already returned - use exists() for better performance
    if Return.objects.filter(Rental=rental).exists():
        messages.warning(request, 'This rental has already been returned.')
        return redirect('reservations')
    
    # Process return
    Return.objects.create(
        Rental=rental,
        ProcessedByUser=admin
    )
    
    # Update copy status back to Available
    rental.Copy.Status = 'Available'
    rental.Copy.save()
    
    # Mark the reservation as completed so user can reserve again
    # Find the reservation that led to this rental (created before the rental)
    reservation = Reservation.objects.filter(
        User=rental.User,
        Book=rental.Copy.Book,
        Status='Active',
        ReservationTime__lte=rental.RentTime  # Only get reservations made before/at rental time
    ).order_by('-ReservationTime').first()  # Get the most recent one before rental
    
    if reservation:
        reservation.Status = 'Completed'
        reservation.save()
    
    messages.success(request, f'Successfully processed return for "{rental.Copy.Book.Title}".')
    return redirect('reservations')


@admin_required
@transaction.atomic
def delete_reservation(request, reservation_id):
    """Admin action to delete a reservation (only if in Reserved phase)"""
    reservation = get_object_or_404(Reservation.objects.select_related('Book', 'User'), ReservationID=reservation_id)
    
    # Check if there's a rental for this reservation - use exists() for better performance
    rental_exists = Rental.objects.filter(
        User=reservation.User,
        Copy__Book=reservation.Book
    ).exclude(
        return__isnull=False
    ).exists()
    
    if rental_exists:
        messages.error(request, 'Cannot delete reservation: book has been issued. Process the return first.')
        return redirect('reservations')
    
    # Free up the reserved copy - use select_for_update to prevent race conditions
    reserved_copy = BookCopy.objects.select_for_update().filter(
        Book=reservation.Book,
        Status='Reserved'
    ).first()
    
    if reserved_copy:
        reserved_copy.Status = 'Available'
        reserved_copy.save()
    
    book_title = reservation.Book.Title
    reservation.delete()
    
    messages.success(request, f'Successfully deleted reservation for "{book_title}".')
    return redirect('reservations')


@admin_required
@transaction.atomic
def update_reservation_dates(request, reservation_id):
    """Admin action to update reservation or rental dates"""
    reservation = get_object_or_404(Reservation, ReservationID=reservation_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_expiry':
            new_expiry = request.POST.get('expiry_time')
            if new_expiry:
                try:
                    expiry_date = datetime.strptime(new_expiry, '%Y-%m-%d')
                    expiry_date = timezone.make_aware(expiry_date.replace(hour=23, minute=59, second=59))
                    
                    reservation.ExpiryTime = expiry_date
                    reservation.save()
                    messages.success(request, 'Reservation expiry date updated.')
                except ValueError:
                    messages.error(request, 'Invalid date format.')
                except Exception as e:
                    messages.error(request, f'Error updating expiry date: {str(e)}')
        
        elif action == 'update_due_date':
            rental = Rental.objects.filter(
                User=reservation.User,
                Copy__Book=reservation.Book
            ).first()
            
            if rental:
                new_due_date = request.POST.get('due_date')
                if new_due_date:
                    try:
                        due_date = datetime.strptime(new_due_date, '%Y-%m-%d')
                        due_date = timezone.make_aware(due_date.replace(hour=23, minute=59, second=59))
                        
                        rental.DueDate = due_date
                        rental.save()
                        messages.success(request, 'Rental due date updated.')
                    except ValueError:
                        messages.error(request, 'Invalid date format.')
                    except Exception as e:
                        messages.error(request, f'Error updating due date: {str(e)}')
    
    return redirect('reservations')


@admin_required
def overdue(request):
    """Display overdue reservations and rentals, with tabs for by-book and by-user views"""
    from Account.models import Account

    now = timezone.now()

    overdue_items = []

    # 1. Expired reservations (Active, past expiry, never progressed to a rental)
    expired_reservations = Reservation.objects.filter(
        Status='Active',
        ExpiryTime__lt=now
    ).select_related('User', 'Book', 'Book__Author', 'Book__Genre')
    
    # Get list of expired reservations
    expired_list = list(expired_reservations)
    
    # Collect user and book IDs
    exp_user_ids = set(r.User_id for r in expired_list)
    exp_book_ids = set(r.Book_id for r in expired_list)
    
    # Fetch all rentals for these users/books in one query
    if exp_user_ids and exp_book_ids:
        exp_rentals = Rental.objects.filter(
            User_id__in=exp_user_ids,
            Copy__Book_id__in=exp_book_ids
        ).values_list('User_id', 'Copy__Book_id', 'RentTime')
        
        # Build a set of (user_id, book_id) that have rentals
        has_rental_set = set((u, b) for u, b, rt in exp_rentals)
    else:
        has_rental_set = set()
    
    for reservation in expired_list:
        key = (reservation.User_id, reservation.Book_id)
        # Check if there's any rental for this user/book combination
        # If it's in our set, skip it
        if key not in has_rental_set:
            overdue_items.append({
                'type': 'reservation',
                'reservation': reservation,
                'rental': None,
                'book': reservation.Book,
                'user': reservation.User,
                'overdue_since': reservation.ExpiryTime,
                'copy': None,
            })

    # 2. Overdue rentals (past due date, no return record)
    overdue_rentals = Rental.objects.filter(
        DueDate__lt=now
    ).select_related(
        'User', 'Copy', 'Copy__Book', 'Copy__Book__Author', 'Copy__Book__Genre'
    ).prefetch_related(
        Prefetch(
            'return_set',
            queryset=Return.objects.all()
        )
    )

    # Build a mapping of (user_id, book_id, rent_time) -> most recent reservation
    rental_users_and_books = [
        (rental.User.UserID, rental.Copy.Book.BookID, rental.RentTime) 
        for rental in overdue_rentals
    ]
    
    # Get all potentially related reservations in one query
    reservation_lookup = {}
    if rental_users_and_books:
        user_ids = set(user_id for user_id, _, _ in rental_users_and_books)
        book_ids = set(book_id for _, book_id, _ in rental_users_and_books)
        
        all_reservations = Reservation.objects.filter(
            User_id__in=user_ids,
            Book_id__in=book_ids
        ).select_related('User', 'Book', 'Book__Author', 'Book__Genre')
        
        # Build lookup: (user_id, book_id, rent_time) -> reservation
        for user_id, book_id, rent_time in rental_users_and_books:
            # Find the most recent reservation before this rental
            matching = [
                res for res in all_reservations 
                if res.User_id == user_id 
                and res.Book_id == book_id 
                and res.ReservationTime <= rent_time
            ]
            if matching:
                # Get the most recent one
                reservation_lookup[(user_id, book_id, rent_time)] = max(
                    matching, 
                    key=lambda r: r.ReservationTime
                )

    for rental in overdue_rentals:
        # Check if there's a return (already prefetched - no query!)
        return_records = list(rental.return_set.all())
        has_return = len(return_records) > 0
        
        if not has_return:
            # Get the associated reservation from our lookup (no query!)
            reservation = reservation_lookup.get(
                (rental.User.UserID, rental.Copy.Book.BookID, rental.RentTime)
            )

            overdue_items.append({
                'type': 'rental',
                'reservation': reservation,
                'rental': rental,
                'book': rental.Copy.Book,
                'user': rental.User,
                'overdue_since': rental.DueDate,
                'copy': rental.Copy,
            })

    # --- By-Book grouping ---
    by_book_map = {}
    for item in overdue_items:
        book_id = item['book'].BookID
        if book_id not in by_book_map:
            by_book_map[book_id] = {
                'book': item['book'],
                'items': [],
            }
        by_book_map[book_id]['items'].append(item)

    by_book = list(by_book_map.values())
    by_book.sort(key=lambda g: len(g['items']), reverse=True)

    # --- By-User grouping ---
    by_user_map = {}
    for item in overdue_items:
        uid = item['user'].UserID
        if uid not in by_user_map:
            by_user_map[uid] = {
                'user': item['user'],
                'items': [],
            }
        by_user_map[uid]['items'].append(item)

    by_user = list(by_user_map.values())
    by_user.sort(key=lambda g: len(g['items']), reverse=True)

    context = {
        'by_book': by_book,
        'by_user': by_user,
        'total_overdue': len(overdue_items),
    }

    return render(request, 'overdue.html', context)