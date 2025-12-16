from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
from models import db, Event, Resource, EventResourceAllocation

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///events.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

# EVENTS

@app.route('/events', methods=['GET', 'POST'])
def events():
    edit_event = None
    event_id = request.args.get('edit_event')
    if event_id:
        edit_event = Event.query.get(int(event_id))

    if request.method == 'POST':
        start = datetime.fromisoformat(request.form['start'])
        end = datetime.fromisoformat(request.form['end'])

        if start >= end:
            return render_template('events.html', events=Event.query.all(),
                                   edit_event=edit_event,
                                   error="Start time must be before end time")

        if request.form.get('event_id'): 
            event = Event.query.get(int(request.form['event_id']))
            event.title = request.form['title']
            event.start_time = start
            event.end_time = end
            event.description = request.form['desc']
        else:  
            event = Event(title=request.form['title'],
                          start_time=start,
                          end_time=end,
                          description=request.form['desc'])
            db.session.add(event)

        db.session.commit()
        return redirect('/events')

    return render_template('events.html', events=Event.query.all(), edit_event=edit_event)

# DELETE EVENT

@app.route('/delete_event/<int:event_id>', methods=['POST'])
def delete_event(event_id):
    EventResourceAllocation.query.filter_by(event_id=event_id).delete()
    event = Event.query.get(event_id)
    if event:
        db.session.delete(event)
        db.session.commit()
    return redirect('/events')

# RESOURCES

@app.route('/resources', methods=['GET', 'POST'])
def resources():
    edit_resource = None
    resource_id = request.args.get('edit_resource')
    if resource_id:
        edit_resource = Resource.query.get(int(resource_id))

    if request.method == 'POST':
        if request.form.get('resource_id'):  
            resource = Resource.query.get(int(request.form['resource_id']))
            resource.resource_name = request.form['name']
            resource.resource_type = request.form['type']
        else: 
            resource = Resource(resource_name=request.form['name'],
                                resource_type=request.form['type'])
            db.session.add(resource)

        db.session.commit()
        return redirect('/resources')

    return render_template('resources.html', resources=Resource.query.all(), edit_resource=edit_resource)

# DELETE RESOURCE

@app.route('/delete_resource/<int:resource_id>', methods=['POST'])
def delete_resource(resource_id):
    EventResourceAllocation.query.filter_by(resource_id=resource_id).delete()
    resource = Resource.query.get(resource_id)
    if resource:
        db.session.delete(resource)
        db.session.commit()
    return redirect('/resources')

# ALLOCATE RESOURCE TO EVENT

@app.route('/allocate', methods=['GET', 'POST'])
def allocate():
    conflicts_detected = []

    if request.method == 'POST':
        event_id = int(request.form['event'])
        resource_id = int(request.form['resource'])
        event = Event.query.get(event_id)

      
        allocations = EventResourceAllocation.query.filter_by(resource_id=resource_id).all()
        conflict_flag = False
        for alloc in allocations:
            e = Event.query.get(alloc.event_id)
            if event.start_time < e.end_time and event.end_time > e.start_time:
                conflict_flag = True
                conflicts_detected.append({
                    'resource': Resource.query.get(resource_id).resource_name,
                    'event1': e.title,
                    'event1_time': f"{e.start_time.strftime('%Y-%m-%d %H:%M')} - {e.end_time.strftime('%H:%M')}",
                    'event2': event.title,
                    'event2_time': f"{event.start_time.strftime('%Y-%m-%d %H:%M')} - {event.end_time.strftime('%H:%M')}"
                })

     
        duplicate = EventResourceAllocation.query.filter_by(event_id=event_id, resource_id=resource_id).first()
        if duplicate:
            return render_template('allocate.html',
                                   events=Event.query.all(),
                                   resources=Resource.query.all(),
                                   error="Resource already allocated to this event.",
                                   conflicts=conflicts_detected)

        
        allocation = EventResourceAllocation(
            event_id=event_id,
            resource_id=resource_id,
            conflict=conflict_flag
        )
        db.session.add(allocation)
        db.session.commit()

        if conflict_flag:
            return render_template('allocate.html',
                                   events=Event.query.all(),
                                   resources=Resource.query.all(),
                                   error="Resource conflicts with another event.",
                                   conflicts=conflicts_detected)

        return redirect(url_for('allocate', success=1))

    success = request.args.get('success')
    return render_template('allocate.html',
                           events=Event.query.all(),
                           resources=Resource.query.all(),
                           success=success,
                           conflicts=[])

# CONFLICTS PAGE

@app.route('/conflicts')
def conflicts():
    conflict_list = []
    allocations = EventResourceAllocation.query.all()
    seen_pairs = set()

    for i in range(len(allocations)):
        for j in range(i + 1, len(allocations)):
            a1, a2 = allocations[i], allocations[j]

            if a1.resource_id != a2.resource_id:
                continue

            e1 = Event.query.get(a1.event_id)
            e2 = Event.query.get(a2.event_id)

            if e1.start_time < e2.end_time and e1.end_time > e2.start_time or a1.conflict or a2.conflict:
                pair_key = tuple(sorted([e1.event_id, e2.event_id, a1.resource_id]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                resource = Resource.query.get(a1.resource_id)
                conflict_list.append({
                    'resource': resource.resource_name,
                    'event1': e1.title,
                    'event1_time': f"{e1.start_time.strftime('%Y-%m-%d %H:%M')} - {e1.end_time.strftime('%H:%M')}",
                    'event2': e2.title,
                    'event2_time': f"{e2.start_time.strftime('%Y-%m-%d %H:%M')} - {e2.end_time.strftime('%H:%M')}"
                })

    return render_template('conflicts.html', conflicts=conflict_list)

# RESOURCE UTILIZATION REPORT

@app.route('/report', methods=['GET', 'POST'])
def report():
    report_data = []
    if request.method == 'POST':
        start = datetime.fromisoformat(request.form['start'])
        end = datetime.fromisoformat(request.form['end'])
        now = datetime.now()

        for resource in Resource.query.all():
            total_hours = 0
            upcoming = 0
            total_events = 0

            allocations = EventResourceAllocation.query.filter_by(resource_id=resource.resource_id).all()
            for alloc in allocations:
                event = Event.query.get(alloc.event_id)
                total_events += 1

                overlap_start = max(start, event.start_time)
                overlap_end = min(end, event.end_time)

                if overlap_start < overlap_end:
                    total_hours += (overlap_end - overlap_start).total_seconds() / 3600

                if event.start_time > now:
                    upcoming += 1

            report_data.append({
                'resource': resource.resource_name,
                'total_events': total_events,
                'hours': round(total_hours, 2),
                'upcoming': upcoming
            })

    return render_template('report.html', report_data=report_data)

# RUN

if __name__ == '__main__':
    app.run(debug=True)
