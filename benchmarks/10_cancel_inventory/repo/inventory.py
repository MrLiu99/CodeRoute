class Inventory:
    def __init__(self, capacity):
        self.available = capacity
        self.bookings = {}

    def book(self, booking_id, seats):
        if booking_id in self.bookings or seats < 1 or seats > self.available:
            raise ValueError('invalid booking')
        self.bookings[booking_id] = seats
        self.available -= seats

    def cancel(self, booking_id):
        seats = self.bookings.pop(booking_id, 0)
        self.available -= seats
