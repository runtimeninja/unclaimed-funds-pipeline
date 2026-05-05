"""CRM export package: scored_leads -> Airtable.

Push un-exported leads to Airtable, then flip exported_to_crm=True and
record the returned airtable_record_id so we don't re-push on the next run.
"""
