# TinyScheduler Operations Guide

Comprehensive guide for operating and maintaining TinyScheduler with queue integration support.

## Table of Contents

- [Daily Operations](#daily-operations)
- [Queue Monitoring](#queue-monitoring)
- [Agent Pool Management](#agent-pool-management)
- [Troubleshooting](#troubleshooting)
- [Performance Tuning](#performance-tuning)
- [Maintenance Procedures](#maintenance-procedures)
- [Emergency Procedures](#emergency-procedures)

## Daily Operations

### Health Checks

**Morning Checklist**:

```bash
# 1. Check scheduler is running
ps aux | grep tinyscheduler

# 2. Check for recent activity
tail -50 state/logs/scheduler_$(date +%Y%m%d).log

# 3. Verify no stale leases
find state/running -name "task_*.json" -mmin +60

# 4. Check error count
grep ERROR state/logs/scheduler_$(date +%Y%m%d).log | wc -l

# 5. Verify agent registry loaded
grep "Loaded agent registry" state/logs/scheduler_$(date +%Y%m%d).log | tail -1
```

**Expected Results**:
- Scheduler process running
- Recent log entries (within loop interval)
- No stale leases older than max_runtime
- Minimal ERROR entries
- Agent registry loaded successfully

### Reconciliation Status

```bash
# View recent reconciliation passes
grep "Starting reconciliation" state/logs/scheduler_*.log | tail -10

# Check reconciliation stats
grep -E "(tasks_spawned|unassigned_matched|assigned_spawned)" state/logs/scheduler_$(date +%Y%m%d).log | tail -20

# View recent task assignments
grep "Assigning task" state/logs/scheduler_*.log | tail -20
```

### Agent Activity

```bash
# Count active leases per agent
for agent in vaela damien oscar kalis; do
  count=$(ls state/running/ | grep -c "$agent" || echo 0)
  echo "$agent: $count active tasks"
done

# Check agent capacity utilization
./tinyscheduler run --once --dry-run 2>&1 | grep "available slots"
```

## Queue Monitoring

### Queue Status Overview

**Check Queue Processing**:

```bash
# View queue processing in logs
grep "Processing queue" state/logs/scheduler_$(date +%Y%m%d).log | tail -20

# Check unassigned task counts per queue
grep "Found.*unassigned tasks in queue" state/logs/scheduler_*.log | tail -10

# View queue types being processed
grep "Agent types (queues)" state/logs/scheduler_*.log | tail -1
```

**Example Output**:
```
INFO - Agent types (queues): dev, qa
INFO - Processing queue 'dev'...
INFO - Found 3 unassigned tasks in queue 'dev'
INFO - Processing queue 'qa'...
INFO - Found 1 unassigned tasks in queue 'qa'
```

### Per-Queue Metrics

Create monitoring script (`scripts/queue-metrics.sh`):

```bash
#!/bin/bash
# Get queue metrics from recent logs

LOG_FILE="state/logs/scheduler_$(date +%Y%m%d).log"

echo "=== Queue Metrics (Last Hour) ==="
echo

for queue in dev qa product infra docs; do
    echo "Queue: $queue"
    
    # Unassigned tasks found
    unassigned=$(grep -a "Found.*unassigned tasks in queue '$queue'" "$LOG_FILE" | \
                 tail -10 | \
                 awk '{print $4}' | \
                 awk '{sum+=$1; count++} END {if(count>0) print sum/count; else print 0}')
    echo "  Avg unassigned tasks: $unassigned"
    
    # Assignments made
    assigned=$(grep -ac "Assigning task.*to.*$queue" "$LOG_FILE" || echo 0)
    echo "  Tasks assigned: $assigned"
    
    echo
done
```

### Queue Depth Tracking

```bash
# Check current queue depth (requires tinytask API access)
curl -s http://localhost:3000/api/queues/dev/tasks?status=idle | jq 'length'
curl -s http://localhost:3000/api/queues/qa/tasks?status=idle | jq 'length'

# Or use tinytask CLI if available
tinytask queue list dev --status idle
```

### Alert Conditions

**Set up alerts for**:
- Queue depth > threshold for extended period
- No tasks assigned in last N reconciliation cycles
- Error rate spike in queue processing
- Specific queue not being processed

**Example Alert Script**:

```bash
#!/bin/bash
# alert-queue-depth.sh

QUEUE="dev"
THRESHOLD=10
LOG_FILE="state/logs/scheduler_$(date +%Y%m%d).log"

# Check recent queue depth
recent_depth=$(grep "Found.*unassigned tasks in queue '$QUEUE'" "$LOG_FILE" | \
               tail -1 | awk '{print $4}')

if [ "$recent_depth" -gt "$THRESHOLD" ]; then
    echo "ALERT: Queue '$QUEUE' depth is $recent_depth (threshold: $THRESHOLD)"
    # Send notification (email, slack, etc.)
fi
```

## Agent Pool Management

### Adding Agents to a Pool

**Procedure**:

1. **Add to agent control file**:
   ```bash
   nano $TINYSCHEDULER_AGENT_CONTROL_FILE
   
   # Add new agent entry:
   # {
   #   "agentName": "newagent",
   #   "agentType": "dev"
   # }
   ```

2. **Add agent limit**:
   ```bash
   # Update tinyscheduler.env
   TINYSCHEDULER_AGENT_LIMITS='{"vaela": 3, "damien": 2, "newagent": 2, ...}'
   ```

3. **Create recipe file**:
   ```bash
   cp recipes/vaela.yaml recipes/newagent.yaml
   # Edit recipe as needed
   ```

4. **Validate configuration**:
   ```bash
   ./tinyscheduler validate-config
   ```

5. **Test in dry-run**:
   ```bash
   ./tinyscheduler run --once --dry-run | grep newagent
   ```

6. **Deploy**:
   ```bash
   # Restart scheduler or wait for next reconciliation
   # (No restart needed for cron-based deployment)
   ```

### Removing Agents from a Pool

**Procedure**:

1. **Wait for active tasks to complete**:
   ```bash
   # Check active tasks for agent
   ls state/running/*newagent* 2>/dev/null
   
   # Wait or manually complete
   ```

2. **Remove from agent control file**:
   ```bash
   nano $TINYSCHEDULER_AGENT_CONTROL_FILE
   # Delete agent entry
   ```

3. **Remove agent limit** (optional):
   ```bash
   # Update tinyscheduler.env if desired
   ```

4. **Validate and deploy**:
   ```bash
   ./tinyscheduler validate-config
   ```

### Adjusting Agent Capacity

**Increase Capacity**:

```bash
# Update agent limits
TINYSCHEDULER_AGENT_LIMITS='{"vaela": 5, "damien": 3, ...}'  # Increased from 3, 2

# No restart needed for cron deployment
# For daemon, restart service
sudo systemctl restart tinyscheduler
```

**Decrease Capacity**:

```bash
# Wait for active tasks to drop below new limit
watch -n 5 'ls state/running/*vaela* | wc -l'

# Update agent limits
TINYSCHEDULER_AGENT_LIMITS='{"vaela": 2, ...}'  # Decreased from 5
```

### Rebalancing Agent Pools

**Scenario**: One agent overloaded, others idle

**Solution**:

1. **Check current distribution**:
   ```bash
   for agent in vaela damien; do
     echo "$agent: $(ls state/running/*$agent* 2>/dev/null | wc -l) tasks"
   done
   ```

2. **Adjust limits to rebalance**:
   ```bash
   # If vaela overloaded, increase capacity or add agents
   # If damien idle, check logs for why tasks not assigned
   ```

3. **Monitor assignment patterns**:
   ```bash
   grep "Assigning task" state/logs/scheduler_$(date +%Y%m%d).log | \
     awk '{print $NF}' | sort | uniq -c
   ```

### Agent Pool Health

```bash
#!/bin/bash
# pool-health.sh - Check health of agent pools

echo "=== Agent Pool Health ==="
echo

for pool in dev qa product; do
    echo "Pool: $pool"
    
    # Get agents in pool
    agents=$(jq -r ".[] | select(.agentType==\"$pool\") | .agentName" \
             $TINYSCHEDULER_AGENT_CONTROL_FILE)
    
    for agent in $agents; do
        active=$(ls state/running/*$agent* 2>/dev/null | wc -l)
        limit=$(grep "$agent" tinyscheduler.env | cut -d: -f2 | tr -d ' ",}')
        echo "  $agent: $active/$limit tasks"
    done
    
    echo
done
```

## Troubleshooting

### Queue-Specific Issues

#### Issue: Tasks Not Being Assigned

**Symptoms**:
- Unassigned tasks in queue
- Agents have available capacity
- No assignment log entries

**Diagnosis**:
```bash
# 1. Check agent registry loaded
grep "Loaded agent registry" state/logs/scheduler_$(date +%Y%m%d).log

# 2. Verify queue types match
jq -r '.[].agentType' $TINYSCHEDULER_AGENT_CONTROL_FILE | sort -u

# 3. Check queue processing
grep "Processing queue" state/logs/scheduler_$(date +%Y%m%d).log | tail -10

# 4. Look for errors
grep ERROR state/logs/scheduler_$(date +%Y%m%d).log | grep -i queue
```

**Solutions**:
- Verify agent control file exists and is valid JSON
- Ensure `agentType` matches actual queue names in tinytask
- Check agent limits are set correctly
- Review logs for specific error messages

#### Issue: Load Imbalance

**Symptoms**:
- One agent consistently gets more tasks
- Other agents in same pool are idle

**Diagnosis**:
```bash
# Check capacity settings
./tinyscheduler config --show | grep -A 20 "Agent Limits"

# Review recent assignments
grep "Assigning task" state/logs/scheduler_*.log | \
  tail -50 | awk '{print $(NF-1), $NF}' | sort | uniq -c
```

**Solutions**:
- Adjust agent limits to balance capacity
- Check if one agent has much higher limit
- Verify all agents in pool have same `agentType`
- Look for repeated failures on one agent (reduces effective capacity)

#### Issue: Queue Not Being Processed

**Symptoms**:
- No log entries for specific queue
- Tasks accumulating in that queue

**Diagnosis**:
```bash
# Check if queue type exists in agent registry
jq -r '.[].agentType' $TINYSCHEDULER_AGENT_CONTROL_FILE | grep -w <queue_name>

# Check if agents for that type exist
jq -r ".[] | select(.agentType==\"<queue_name>\") | .agentName" \
  $TINYSCHEDULER_AGENT_CONTROL_FILE

# Look for queue-specific errors
grep "<queue_name>" state/logs/scheduler_$(date +%Y%m%d).log
```

**Solutions**:
- Add agents for that queue type to agent control file
- Check agent limits configured for those agents
- Verify tinytask queue name matches `agentType`

### Agent Registry Issues

#### Issue: Agent Control File Won't Load

**Diagnosis**:
```bash
# Check file exists
ls -l $TINYSCHEDULER_AGENT_CONTROL_FILE

# Validate JSON syntax
python3 -m json.tool $TINYSCHEDULER_AGENT_CONTROL_FILE

# Check permissions
ls -l $TINYSCHEDULER_AGENT_CONTROL_FILE
```

**Solutions**:
```bash
# Fix JSON syntax errors
nano $TINYSCHEDULER_AGENT_CONTROL_FILE

# Fix permissions if needed
chmod 644 $TINYSCHEDULER_AGENT_CONTROL_FILE

# Validate
./tinyscheduler validate-config
```

#### Issue: Agent Not Recognized

**Symptoms**:
- Agent in control file but no tasks assigned
- Warnings about missing recipes

**Diagnosis**:
```bash
# Check agent name spelling
jq -r '.[].agentName' $TINYSCHEDULER_AGENT_CONTROL_FILE

# Check agent limits
./tinyscheduler config --show | grep -i <agent_name>

# Check recipe exists
ls recipes/<agent_name>.yaml
```

**Solutions**:
- Fix typos in agent names (must match exactly)
- Add agent to `TINYSCHEDULER_AGENT_LIMITS`
- Create missing recipe file

### Performance Issues

#### Issue: Slow Reconciliation

**Symptoms**:
- Reconciliation takes longer than loop interval
- Overlapping scheduler runs

**Diagnosis**:
```bash
# Check reconciliation duration
grep -A 30 "Starting reconciliation" state/logs/scheduler_$(date +%Y%m%d).log | \
  grep "Reconciliation completed"

# Check for lock file issues
cat state/tinyscheduler.lock
```

**Solutions**:
- Increase loop interval
- Reduce number of agents/queues
- Check tinytask server performance
- Review for excessive error retries

#### Issue: High Error Rate

**Symptoms**:
- Many ERROR entries in logs
- Tasks not progressing

**Diagnosis**:
```bash
# Count errors per hour
grep ERROR state/logs/scheduler_$(date +%Y%m%d).log | \
  awk '{print $1}' | cut -d: -f1 | sort | uniq -c

# Identify error types
grep ERROR state/logs/scheduler_$(date +%Y%m%d).log | \
  awk -F'ERROR - ' '{print $2}' | sort | uniq -c | sort -rn
```

**Solutions**:
- Check tinytask server connectivity
- Verify agent limits are reasonable
- Review spawn failures (goose issues)
- Check file system permissions

### Blocked Task Issues

#### Issue: Tasks Not Spawning Despite Available Capacity

**Symptoms**:
- Tasks visible in tinytask queue
- Agents have available slots
- No tasks spawning
- "Blocked tasks skipped" in logs

**Diagnosis**:
```bash
# Check if blocking is filtering tasks
./tinyscheduler run --once | grep "Filtered out"

# View blocked task count
./tinyscheduler run --once | grep "Blocked tasks skipped"

# Check task blocking status in tinytask
curl -s http://localhost:3000/api/tasks | jq '.[] | {id, is_currently_blocked, blocked_by_task_id}'
```

**Solutions**:
- Complete or unblock the blocking tasks
- Verify TinyTask blocking relationships are correct
- Check if blocker tasks are stuck or failed
- Temporarily disable blocking if needed: `TINYSCHEDULER_DISABLE_BLOCKING=1`

#### Issue: Wrong Tasks Being Prioritized

**Symptoms**:
- Lower priority tasks spawned before high priority
- Tasks spawn in unexpected order

**Diagnosis**:
```bash
# Check if blocker prioritization is active
grep "Prioritizing.*blocker task" state/logs/scheduler_$(date +%Y%m%d).log

# View task sorting details
grep "blocks.*task(s)" state/logs/scheduler_$(date +%Y%m%d).log
```

**Explanation**:
- Blocker tasks are intentionally prioritized over high-priority tasks
- This maximizes throughput by unblocking dependencies faster
- Within blocker tasks, priority is still respected

**Solution**:
- This is expected behavior for blocking-aware scheduling
- To disable, use `TINYSCHEDULER_DISABLE_BLOCKING=1`

#### Issue: Blocked Tasks Accumulating

**Symptoms**:
- Many tasks in blocked state
- Blocked count increasing over time

**Diagnosis**:
```bash
# Check blocker task status
grep "Task.*blocks.*task(s)" state/logs/scheduler_$(date +%Y%m%d).log

# Monitor blocked task count over time
watch -n 30 './tinyscheduler run --once --dry-run | grep "Blocked tasks skipped"'
```

**Solutions**:
- Investigate why blocker tasks aren't completing
- Check for blocking chains (A blocks B blocks C)
- Review tinytask task dependencies
- Consider breaking up task dependencies

## Performance Tuning

### Optimization Guidelines

**Loop Interval**:
```bash
# Default: 60 seconds
TINYSCHEDULER_LOOP_INTERVAL_SEC=60

# High-frequency (for fast task assignment):
TINYSCHEDULER_LOOP_INTERVAL_SEC=30

# Low-frequency (for low priority queues):
TINYSCHEDULER_LOOP_INTERVAL_SEC=120
```

**Agent Capacity**:
```bash
# Start conservative
TINYSCHEDULER_AGENT_LIMITS='{"vaela": 2, ...}'

# Increase based on:
# - System resources (CPU, memory)
# - Task complexity
# - Average task duration
# - Concurrent I/O limits

# Production example (beefy server):
TINYSCHEDULER_AGENT_LIMITS='{"vaela": 5, "damien": 5, "oscar": 3}'
```

**Heartbeat Interval**:
```bash
# Default: 15 seconds
TINYSCHEDULER_HEARTBEAT_SEC=15

# More aggressive stale detection:
TINYSCHEDULER_HEARTBEAT_SEC=10

# Reduce file I/O:
TINYSCHEDULER_HEARTBEAT_SEC=30
```

### Queue-Specific Tuning

**High-Priority Queues**:
- Allocate more agents to pool
- Higher agent capacity limits
- Monitor queue depth closely

**Low-Priority Queues**:
- Fewer agents
- Lower capacity limits
- Can tolerate queue buildup

**Mixed Workloads**:
```json
{
  "vaela": 5,    // Dev: high capacity
  "damien": 5,   // Dev: high capacity
  "oscar": 3,    // QA: medium capacity
  "kalis": 2,    // QA: medium capacity
  "sage": 1,     // Product: low capacity
  "atlas": 2     // Docs: low capacity
}
```

### Capacity Planning

**Formula**:
```
Optimal Capacity = (Tasks per Hour) / (Average Task Duration in Hours) / (Number of Agents in Pool)
```

**Example**:
- Tasks per hour: 30
- Average duration: 20 minutes (0.33 hours)
- Agents in pool: 2 (vaela, damien)

```
Capacity per agent = 30 / 0.33 / 2 = ~45 concurrent tasks
```

(In practice, start lower and increase based on monitoring)

## Maintenance Procedures

### Log Rotation

```bash
# Automatic log rotation (logrotate config)
cat > /etc/logrotate.d/tinyscheduler << 'EOF'
/home/user/workspace/calypso/state/logs/scheduler_*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
EOF
```

### State Directory Cleanup

```bash
#!/bin/bash
# cleanup-old-leases.sh - Remove very old lease files

LEASE_DIR="state/running"
MAX_AGE_DAYS=7

find "$LEASE_DIR" -name "task_*.json" -mtime +$MAX_AGE_DAYS -exec rm {} \;

echo "Cleaned up leases older than $MAX_AGE_DAYS days"
```

### Agent Control File Backup

```bash
# Backup before changes
cp $TINYSCHEDULER_AGENT_CONTROL_FILE \
   ${TINYSCHEDULER_AGENT_CONTROL_FILE}.backup.$(date +%Y%m%d)

# Keep last 10 backups
ls -t ${TINYSCHEDULER_AGENT_CONTROL_FILE}.backup.* | tail -n +11 | xargs rm -f
```

### Configuration Audit

```bash
#!/bin/bash
# audit-config.sh - Check configuration consistency

echo "=== TinyScheduler Configuration Audit ==="
echo

# 1. Check agent control file
echo "Agent Control File: $TINYSCHEDULER_AGENT_CONTROL_FILE"
if [ -f "$TINYSCHEDULER_AGENT_CONTROL_FILE" ]; then
    echo "  ✓ File exists"
    if python3 -m json.tool "$TINYSCHEDULER_AGENT_CONTROL_FILE" > /dev/null 2>&1; then
        echo "  ✓ Valid JSON"
        agent_count=$(jq 'length' "$TINYSCHEDULER_AGENT_CONTROL_FILE")
        echo "  ✓ $agent_count agents defined"
    else
        echo "  ✗ Invalid JSON"
    fi
else
    echo "  ✗ File not found"
fi

echo

# 2. Check agent limits match
echo "Agent Limit Consistency:"
agents_in_control=$(jq -r '.[].agentName' "$TINYSCHEDULER_AGENT_CONTROL_FILE" | sort)
agents_in_limits=$(./tinyscheduler config --show --json | jq -r '.agent_limits | keys[]' | sort)

echo "  Agents in control file: $(echo $agents_in_control | tr '\n' ' ')"
echo "  Agents with limits: $(echo $agents_in_limits | tr '\n' ' ')"

echo

# 3. Check recipe files
echo "Recipe Files:"
for agent in $agents_in_control; do
    if [ -f "recipes/$agent.yaml" ]; then
        echo "  ✓ recipes/$agent.yaml"
    else
        echo "  ✗ recipes/$agent.yaml (MISSING)"
    fi
done
```

## Emergency Procedures

### Stop All Task Processing

```bash
# 1. Stop scheduler
sudo systemctl stop tinyscheduler
# OR for cron-based:
sudo mv /etc/cron.d/tinyscheduler /etc/cron.d/tinyscheduler.disabled

# 2. Wait for active tasks to complete OR kill them
# List active tasks
ls state/running/

# Kill specific task (if needed)
kill $(jq -r .pid state/running/task_1234.json)

# Clean up lease
rm state/running/task_1234.json
```

### Emergency Agent Removal

```bash
# 1. Remove from agent control file
jq 'del(.[] | select(.agentName=="<agent>"))' \
   $TINYSCHEDULER_AGENT_CONTROL_FILE > /tmp/control.json
mv /tmp/control.json $TINYSCHEDULER_AGENT_CONTROL_FILE

# 2. Wait for active tasks to complete
while ls state/running/*<agent>* 2>/dev/null; do
    echo "Waiting for <agent> tasks to complete..."
    sleep 10
done

# 3. Restart scheduler
# (automatic for cron-based deployment)
```

### Recover from Stuck Reconciliation

```bash
# 1. Check for lock file
cat state/tinyscheduler.lock

# 2. Verify process is actually running
ps aux | grep $(cat state/tinyscheduler.lock)

# 3. If process dead, remove lock
rm state/tinyscheduler.lock

# 4. If process hung, kill it
kill $(cat state/tinyscheduler.lock)
rm state/tinyscheduler.lock
```

### Rollback Queue Integration

```bash
# 1. Backup current agent control file
mv $TINYSCHEDULER_AGENT_CONTROL_FILE \
   ${TINYSCHEDULER_AGENT_CONTROL_FILE}.disabled

# 2. Scheduler will automatically fall back to legacy mode
./tinyscheduler run --once --dry-run

# 3. Verify legacy mode active
# Should see: "Queue-based processing will be disabled. Using legacy agent_limits only."

# 4. To restore queue integration
mv ${TINYSCHEDULER_AGENT_CONTROL_FILE}.disabled \
   $TINYSCHEDULER_AGENT_CONTROL_FILE
```

## Best Practices

1. **Always test in dry-run** before deploying configuration changes
2. **Monitor queue depth** to detect assignment issues early
3. **Keep agent pools balanced** to avoid overloading single agents
4. **Backup agent control file** before making changes
5. **Review logs daily** for errors and warnings
6. **Document agent additions/removals** for audit trail
7. **Use validation tools** before deploying changes
8. **Plan capacity** based on workload patterns
9. **Keep recipes simple** to reduce spawn failures
10. **Monitor task durations** to tune capacity settings

## Monitoring Checklist

**Daily**:
- [ ] Check scheduler is running
- [ ] Review error count
- [ ] Verify recent reconciliation activity
- [ ] Check for stale leases

**Weekly**:
- [ ] Review capacity utilization
- [ ] Audit agent pool balance
- [ ] Check queue depths and trends
- [ ] Review failed task patterns

**Monthly**:
- [ ] Audit configuration consistency
- [ ] Review and tune capacity limits
- [ ] Clean up old logs and leases
- [ ] Update documentation

## Additional Resources

- [TinyScheduler README](../tinyscheduler-README.md) - Full documentation
- [Migration Guide](./tinyscheduler-migration-guide.md) - Migrating to queue integration
- [Technical Plan](./tinyscheduler-queue-integration.md) - Implementation details
- [Example Configurations](../../examples/agent-control-examples/) - Production examples

## Support

For operational issues:
1. Check this operations guide
2. Review logs: `state/logs/scheduler_*.log`
3. Run validation: `./tinyscheduler validate-config`
4. Test in dry-run: `./tinyscheduler run --once --dry-run`
5. Consult troubleshooting section above
