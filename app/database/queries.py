"""Only application-owned SQL fragments; user input is always bound as values."""
PRIORITIES = ('1 - Critical', '2 - High', '3 - Moderate', '4 - Low')
STATES = ('New', 'Resolved', 'Closed', 'Active', 'Awaiting User Info', 'Awaiting Problem', 'Awaiting Vendor', 'Awaiting Evidence', 'Unknown')

def where(filters, alias='s'):
    conditions, values = [], []
    for field, column in [('priority', 'latest_observed_priority'), ('state', 'latest_observed_incident_state_clean'), ('assignment_group', 'assignment_group')]:
        value = getattr(filters, field)
        if value is not None:
            conditions.append(f'{alias}.{column} = ?')
            values.append(value)
    if filters.start_date:
        conditions.append(f'{alias}.opened_at >= ?')
        values.append(filters.start_date.isoformat() + ' 00:00:00')
    if filters.end_date:
        # Inclusive calendar date; no timezone conversion.
        conditions.append(f'{alias}.opened_at <= ?')
        values.append(filters.end_date.isoformat() + ' 23:59:59')
    return (' WHERE ' + ' AND '.join(conditions) if conditions else ''), values
