/**
 * Campus Resource Conflict Resolver - Booking Form Validation & Conflict Checker
 * Handles dynamic timeslot validation, Flatpickr calendar/timer setup, and async conflict detection
 */
document.addEventListener('DOMContentLoaded', function () {
    const resourceSelect = document.getElementById('id_resource');
    const startInput = document.getElementById('id_start_time');
    const endInput = document.getElementById('id_end_time');
    const submitBtn = document.getElementById('submitBookingBtn');

    const conflictBox = document.getElementById('liveConflictBox');
    const conflictIcon = document.getElementById('liveConflictIcon');
    const conflictTitle = document.getElementById('liveConflictTitle');
    const conflictMsg = document.getElementById('liveConflictMsg');

    if (!startInput || !endInput) {
        return; // Not on the booking form
    }

    let debounceTimer = null;

    // Initialize Flatpickr Interactive Calendar & Time Picker
    const fpConfig = {
        enableTime: true,
        dateFormat: "Y-m-d\\TH:i",
        altInput: true,
        altFormat: "F j, Y  —  h:i K",
        altInputClass: "form-control",
        minDate: "today",
        time_24hr: false,
        minuteIncrement: 15,
        defaultHour: 9,
        defaultMinute: 0,
        onChange: function() {
            debouncedCheck();
        }
    };

    let startPicker = null;
    let endPicker = null;

    if (typeof flatpickr !== 'undefined') {
        startPicker = flatpickr(startInput, {
            ...fpConfig,
            onChange: function(selectedDates) {
                if (selectedDates[0] && endPicker) {
                    endPicker.set('minDate', selectedDates[0]);
                }
                debouncedCheck();
            }
        });

        endPicker = flatpickr(endInput, {
            ...fpConfig,
            defaultHour: 10,
            onChange: function() {
                debouncedCheck();
            }
        });
    }

    function renderFeedback(state, title, message) {
        if (!conflictBox) return;

        conflictBox.classList.remove('d-none', 'alert-danger', 'alert-warning', 'alert-success', 'alert-info');
        conflictBox.style.backdropFilter = 'blur(16px)';

        if (state === 'checking') {
            conflictBox.classList.add('alert-info');
            conflictBox.style.borderColor = 'rgba(56, 189, 248, 0.4)';
            conflictBox.style.background = 'rgba(12, 74, 110, 0.35)';
            conflictIcon.className = 'spinner-border spinner-border-sm text-info';
            conflictTitle.className = 'fw-bold small text-info';
            conflictTitle.textContent = title;
            conflictMsg.className = 'small text-white-50';
            conflictMsg.textContent = message;
        } else if (state === 'available') {
            conflictBox.classList.add('alert-success');
            conflictBox.style.borderColor = 'rgba(16, 185, 129, 0.4)';
            conflictBox.style.background = 'rgba(6, 78, 59, 0.35)';
            conflictIcon.className = 'bi bi-check-circle-fill text-success fs-5';
            conflictTitle.className = 'fw-bold small text-success';
            conflictTitle.textContent = title;
            conflictMsg.className = 'small text-white';
            conflictMsg.textContent = message;
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.classList.remove('opacity-50');
            }
        } else if (state === 'conflict') {
            conflictBox.classList.add('alert-danger');
            conflictBox.style.borderColor = 'rgba(244, 63, 94, 0.4)';
            conflictBox.style.background = 'rgba(136, 19, 55, 0.35)';
            conflictIcon.className = 'bi bi-x-octagon-fill text-danger fs-5';
            conflictTitle.className = 'fw-bold small text-danger';
            conflictTitle.textContent = title;
            conflictMsg.className = 'small text-white';
            conflictMsg.textContent = message;
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.classList.add('opacity-50');
            }
        } else if (state === 'warning') {
            conflictBox.classList.add('alert-warning');
            conflictBox.style.borderColor = 'rgba(245, 158, 11, 0.4)';
            conflictBox.style.background = 'rgba(120, 53, 15, 0.35)';
            conflictIcon.className = 'bi bi-exclamation-triangle-fill text-warning fs-5';
            conflictTitle.className = 'fw-bold small text-warning';
            conflictTitle.textContent = title;
            conflictMsg.className = 'small text-white-50';
            conflictMsg.textContent = message;
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.classList.remove('opacity-50');
            }
        } else {
            conflictBox.classList.add('d-none');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.classList.remove('opacity-50');
            }
        }
    }

    function checkSlotAvailability() {
        const resourceId = resourceSelect ? resourceSelect.value : '';
        const startTime = startInput ? startInput.value : '';
        const endTime = endInput ? endInput.value : '';

        if (!resourceId || !startTime || !endTime) {
            if (conflictBox) conflictBox.classList.add('d-none');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.classList.remove('opacity-50');
            }
            return;
        }

        // Quick client-side sanity check
        const startDt = new Date(startTime);
        const endDt = new Date(endTime);

        if (startDt >= endDt) {
            renderFeedback('conflict', 'Invalid Time Interval', 'Start time must be strictly earlier than end time.');
            return;
        }

        if (startDt < new Date()) {
            renderFeedback('conflict', 'Past Date Selected', 'Reservations cannot be created for past dates.');
            return;
        }

        renderFeedback('checking', 'Verifying Timeslot Availability...', 'Checking database for overlapping bookings and maintenance blackouts...');

        const checkApiUrl = document.getElementById('bookingForm') ? document.getElementById('bookingForm').dataset.checkUrl : '/bookings/api/check-conflict/';
        const params = new URLSearchParams({
            resource_id: resourceId,
            start_time: startTime,
            end_time: endTime
        });

        fetch(`${checkApiUrl}?${params.toString()}`)
            .then(response => response.json())
            .then(data => {
                if (data.available) {
                    renderFeedback('available', 'Slot Available & Ready!', data.message);
                } else if (data.conflict_type === 'MAINTENANCE') {
                    renderFeedback('conflict', 'Maintenance Conflict Detected', data.message);
                } else if (data.conflict_type === 'BOOKING') {
                    renderFeedback('conflict', 'Reservation Conflict Detected', data.message);
                } else {
                    renderFeedback('warning', 'Scheduling Notice', data.message);
                }
            })
            .catch(err => {
                console.error('Availability check failed:', err);
                renderFeedback('warning', 'Network Check Error', 'Could not verify slot automatically. You may still try to submit.');
            });
    }

    function debouncedCheck() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(checkSlotAvailability, 350);
    }

    if (resourceSelect) resourceSelect.addEventListener('change', debouncedCheck);
    if (startInput) startInput.addEventListener('input', debouncedCheck);
    if (endInput) endInput.addEventListener('input', debouncedCheck);

    if (resourceSelect && resourceSelect.value && startInput && startInput.value && endInput && endInput.value) {
        checkSlotAvailability();
    }
});
