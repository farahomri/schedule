---
config:
  layout: dagre
---
flowchart TB
    Start(["User Logs In:<br>Assembly Manager"]) --> CheckWeek{"Start of Week<br>OR<br>Fully New Orders?"}
    CheckWeek -- "Yes - Monday Start" --> WeeklyPrep["WEEKLY CYCLE:<br>Wed: FST → Warehouse preplanning<br>Thu: Warehouse → BSHP commissions<br>Fri-Mon: BSHP processing<br>Mon AM: Orders ready"]
    WeeklyPrep --> UploadOrders["Upload Ready Orders File<br>From: BSHP + Warehouse<br>Must cover: 2+ business days<br>Format: Excel/CSV"]
    UploadOrders --> CheckLateOrders{"Any Late Orders<br>from Last Week?"}
    CheckLateOrders -- Yes --> AddLateOrders["ADD Late Orders:<br>- Not completed orders<br>- Previously blocked orders<br>- Merge with new orders"]
    CheckLateOrders -- No --> ProceedAnalysis["Proceed to Analysis"]
    AddLateOrders --> MergeOrderPools["MERGE ORDER POOLS:<br>- New orders status: not_started<br>- Late orders status: preserve existing<br>- Update priorities if changed"]
    MergeOrderPools --> ProceedAnalysis
    CheckWeek -- "No - Continue Week" --> LoadPrevious@{ label: "Auto-Load Previous State:<br>- Yesterday's schedule<br>- All order statuses<br>- Graphs &amp; metrics<br>- Technician summaries" }
    LoadPrevious --> DisplayDashboard["Display Dashboard:<br>✅ Completed orders<br>⏳ In-progress orders<br>🚫 Blocked orders<br>📋 Not-started orders<br>📊 Graphs &amp; Stats"]
    DisplayDashboard --> AskNewOrders{"New Orders<br>Ready to Upload?"}
    AskNewOrders -- No --> ContinueExisting["Continue with Existing:<br>Work on not-started orders<br>from previous days"]
    AskNewOrders -- Yes --> UploadNewOrders["Upload New Orders File<br>Will merge with existing pool"]
    UploadNewOrders --> CheckUpdates{"Check for<br>Order Updates?"}
    CheckUpdates -- Yes --> ProcessUpdates["PROCESS ORDER UPDATES:<br>- Compare with master orders file<br>- Identify: Modified orders<br>- Identify: New orders<br>- Apply updates to database"]
    ProcessUpdates --> ShowUpdateSummary["Show Update Summary:<br>✏️ X orders modified<br>➕ Y new orders added<br>⏭️ Z skipped unchanged"]
    ShowUpdateSummary --> AnalyzeNew["Analyze New Orders"]
    CheckUpdates -- No --> AnalyzeNew
    ProceedAnalysis --> ShiftManagement{"Shift File<br>Management"}
    AnalyzeNew --> AnalyzeOrders["Analyze Uploaded Orders"]
    AnalyzeOrders --> CheckWorkplace{"Does Order Need<br>Specific Workplace?"}
    CheckWorkplace -- Yes --> AssignWorkplace["Assign to Specific Workplace:<br>- Welding Area<br>- Assembly Area<br>- Paint Booth<br>- Testing Station<br>Mark workplace as BUSY<br>for routing time duration"]
    CheckWorkplace -- No --> MarkAnyWorkplace["Mark: Any Workplace OK<br>Not specific requirement"]
    AssignWorkplace --> CheckSplit{"Is Order Large?<br>Should be Split?"}
    MarkAnyWorkplace --> CheckSplit
    CheckSplit -- Yes --> SplitProcess["SPLIT PROCESS:<br>Divide by Quantity<br>Example: Qty 10 → 2 orders of 5 each"]
    CheckSplit -- No --> AddToPool["Add ALL Orders to Pool:<br>Status: not_started<br>Workplace assignment<br>Split info if applicable"]
    SplitProcess --> CreateChildren["Create Child Orders:<br>Parent: ORD-001<br>Child A: ORD-001-A Qty: 5<br>Child B: ORD-001-B Qty: 5"]
    CreateChildren --> DistributeTime["Distribute Routing Time:<br>Total time split between children<br>Each child: Independent tracking"]
    DistributeTime --> AddToPool
    AddToPool --> ShiftManagement
    ShiftManagement -- Upload New File --> UploadShift1["Upload Shift File<br>Details: Technician availability<br>Working hours, breaks, expertise"]
    ShiftManagement -- Use Displayed Shift --> DisplayedShift@{ label: "VIEW &amp; EDIT DISPLAYED SHIFT:<br>- Shows yesterday's shift as default<br>- Manager can modify:<br>  • Working status Yes/No<br>  • Break duration<br>  • Extra time<br>  • To another assignment<br>- Auto-saves changes<br>- No file upload needed" }
    DisplayedShift --> TechnicianCRUD{"Manager wants to<br>Update Technicians?"}
    TechnicianCRUD -- Yes --> ManageTechnicians["MANAGE TECHNICIANS:<br>➕ Add new technician<br>✏️ Modify: Name, Expertise, Certifications<br>🗑️ Delete/Deactivate technician<br>Changes saved to database"]
    TechnicianCRUD -- No --> AnalyzeShift["Analyze Shift:<br>Calculate available time per tech<br>- Base: 8 hours<br>- Minus: Breaks<br>- Plus: Extra time<br>Get expertise levels"]
    ManageTechnicians --> AnalyzeShift
    ContinueExisting --> ShiftManagement
    UploadShift1 --> AnalyzeShift
    AnalyzeShift --> CheckPreviousInProgress{"Any In-Progress<br>Orders from Yesterday?"}
    CheckPreviousInProgress -- Yes --> LoopInProgress{"For Each<br>In-Progress Order"}
    CheckPreviousInProgress -- No --> CheckBlocked{"Any Blocked Orders<br>from Yesterday?"}
    LoopInProgress --> CheckTechToday{"Is Assigned Tech<br>Working Today?"}
    CheckTechToday -- Yes --> KeepAssignment["✅ Keep Assignment:<br>Same tech continues<br>Preserve progress"]
    CheckTechToday -- No --> FindReplacement["Find Replacement:<br>Nearest skill match<br>Must NOT have in-progress<br>orders from yesterday"]
    FindReplacement --> ReassignOrder["Reassign Order:<br>Update assigned tech<br>Log reason: Tech absent<br>Preserve progress %"]
    KeepAssignment --> LoopInProgress
    ReassignOrder --> LoopInProgress
    LoopInProgress -- All Checked --> CheckBlocked
    CheckBlocked -- Yes --> LoopBlocked{"For Each<br>Blocked Order"}
    CheckBlocked -- No --> LoadAssignable["Load Assignable Orders:<br>From order pool:<br>- not_started<br>- not_blocked"]
    LoopBlocked --> CheckUnblocked{"Is Order<br>Unblocked Now?"}
    CheckUnblocked -- Yes --> CheckBlockedTech{"Original Tech<br>Available Today?"}
    CheckUnblocked -- No --> KeepBlocked["Keep Status: Blocked<br>Will check again later"]
    CheckBlockedTech -- Yes --> UnblockAssign["Unblock &amp; Assign:<br>Same tech continues"]
    CheckBlockedTech -- No --> UnblockReassign["Unblock &amp; Reassign:<br>Find new tech"]
    UnblockAssign --> LoopBlocked
    UnblockReassign --> LoopBlocked
    KeepBlocked --> LoopBlocked
    LoopBlocked -- All Checked --> LoadAssignable
    LoadAssignable --> SortOrders["Sort Orders by Priority:<br>1st: Urgent/0<br>2nd: A<br>3rd: B<br>4th: C<br>5th: None<br>Within same priority:<br>Sort by routing time DESC"]
    SortOrders --> Round1["ROUND 1: ROUND-ROBIN<br>Goal: Balance initial workload"]
    Round1 --> RR_Loop{"For Each<br>Technician"}
    RR_Loop --> RR_Find["Find Best Match Order:<br>- Skills match<br>- Expertise level match<br>- Workplace available<br>- Has enough time"]
    RR_Find --> RR_Assign["Assign Order:<br>Mark tech as assigned<br>Reduce available time"]
    RR_Assign --> RR_Loop
    RR_Loop -- All Techs Have 1 Order --> Round2["ROUND 2 &amp; 3: CAPACITY FILL<br>Goal: Maximize utilization"]
    Round2 --> R23_Loop{"For Each<br>Remaining Order"}
    R23_Loop --> R23_Find["Find Most Available Tech:<br>- Most remaining time<br>- Skills match<br>- Expertise adequate"]
    R23_Find --> R23_Assign["Assign Order:<br>Reduce tech available time<br>Track assigned time"]
    R23_Assign --> R23_Loop
    R23_Loop -- All Orders Assigned<br>OR<br>No More Capacity --> GenerateSchedule["Generate Final Schedule:<br>All assignments complete<br>Calculate utilization per tech"]
    GenerateSchedule --> DisplaySchedule["Display Schedule:<br>✅ Orders by technician<br>📊 Utilization graphs<br>📈 Priority distribution<br>🏭 Workplace allocation<br>⏱️ Time tracking setup"]
    DisplaySchedule --> WorkBegins(["Work Begins:<br>Technicians Access System"])
    WorkBegins --> TechInterface["TECHNICIAN INTERFACE:<br>View assigned orders<br>Can: Start, Stop, End, Block"]
    TechInterface --> TechAction{"Technician<br>Action"}
    TechAction -- Click START --> StartOrder["▶️ START ORDER:<br>Status: not_started → started<br>Record 1st start time<br>Start work session timer<br>Update &amp; Save"]
    TechAction -- Click STOP --> StopOrder["⏸️ STOP ORDER:<br>Status: started → stopped<br>Stop timer<br>Record time spent<br>Calculate remaining time<br>Can resume later<br>Update &amp; Save"]
    TechAction -- Click BLOCK --> BlockOrder["🚫 BLOCK ORDER:<br>Status: → blocked<br>Record block time<br>MUST specify reason<br>Notify system"]
    BlockOrder --> NotifyNext["Notify Technician:<br>Will work on next order in pool<br>until block resolved"]
    TechAction -- Click END --> EndOrder["✅ END ORDER:<br>Status: → completed<br>Calculate total spent time<br>Record completion time"]
    EndOrder --> CheckSplitEnd{"Is This<br>Split Order?"}
    CheckSplitEnd -- Yes --> CheckSiblings{"Both Children<br>ORD-001-A &amp; ORD-001-B<br>Completed?"}
    CheckSplitEnd -- No --> MoveCompleted["Move to Completed Pool:<br>Remove from active orders<br>Add to completed_orders table"]
    CheckSiblings -- Yes --> MergeSplit["Merge Split Orders:<br>Parent ORD-001: Completed<br>Combine total times<br>Credit both technicians"]
    CheckSiblings -- No --> PartialSplit["Parent Status:<br>Partially Completed<br>Waiting for sibling"]
    MergeSplit --> MoveCompleted
    PartialSplit --> SaveState["💾 Auto-Save State:<br>Update database<br>Order statuses<br>Work sessions<br>Timestamps"]
    MoveCompleted --> FreeWorkplace{"Was Workplace<br>Assigned?"}
    FreeWorkplace -- Yes --> ReleaseWorkplace["Free Workplace:<br>Mark as available<br>Can assign new orders"]
    FreeWorkplace -- No --> SaveState
    ReleaseWorkplace --> SaveState
    NotifyNext --> SaveState
    StartOrder --> SaveState
    StopOrder --> SaveState
    SaveState --> MoreWork{"More Work<br>Today?"} & FSTInterface["FST DEPARTMENT INTERFACE:<br>Real-time order status view<br>📊 Live charts &amp; graphs<br>📈 Progress tracking<br>Can: Add comments<br>Can: Change priority<br>Monitor assembly floor"]
    MoreWork -- Yes --> TechInterface
    MoreWork -- No --> EndDay["End of Day"]
    FSTInterface --> FSTActions{"FST<br>Actions"}
    FSTActions -- Add Comment --> AddComment["Add Comment to Order:<br>Visible to techs &amp; admin<br>Timestamped &amp; tracked"]
    FSTActions -- Change Priority --> ChangePriority["Change Order Priority:<br>Urgent / A / B / C"]
    ChangePriority --> CheckIfUrgent{"Is New Priority<br>URGENT?"}
    CheckIfUrgent -- Yes --> UrgentProcess["🚨 URGENT PRIORITY PROCESS"]
    CheckIfUrgent -- No --> StandardUpdate["Standard Priority Update:<br>- Update priority in database<br>- Re-sort order queue<br>- Notify assembly manager<br>- Affected techs notified"]
    UrgentProcess --> FindUrgentTech["Find Most Suitable Technician:<br>1. Most available time<br>2. Matching expertise<br>3. Currently working or not"]
    FindUrgentTech --> CheckTechAvail{"Is Any Tech<br>Available Now?"}
    CheckTechAvail -- "Yes - Tech Available" --> QuickAssign["QUICK ASSIGN:<br>- Assign to available tech<br>- Move to top of queue<br>- Tech notified immediately<br>- Starts within 5 minutes"]
    CheckTechAvail -- "No - All Busy" --> ShowOptions["SHOW MANAGER OPTIONS:<br>All techs currently working"]
    ShowOptions --> DisplayBusyTechs["Display Busy Technicians:<br>For each tech show:<br>- Current order working on<br>- Progress % 25%, 50%, etc.<br>- Time remaining<br>- Can interrupt? Yes/No"]
    DisplayBusyTechs --> ManagerDecision{"Manager<br>Decision"}
    ManagerDecision -- Wait --> QueueUrgent["Queue as Next:<br>- Urgent order waits<br>- Will be first when tech free<br>- Estimated wait time shown"]
    ManagerDecision -- Manual Stop --> ManagerStop["MANUAL STOP PROCESS:<br>1. Select technician to stop<br>2. System asks confirmation<br>3. Stop current order pause<br>4. Assign urgent order<br>5. Notify tech of switch<br>6. Paused order queued"]
    ManagerStop --> StopCurrentOrder["Stop Current Order:<br>- Save progress<br>- Status: Paused by manager<br>- Reason: Urgent priority<br>- Queue for resumption"]
    StopCurrentOrder --> AssignUrgent["Assign Urgent Order:<br>- Tech notified<br>- Reason explained<br>- Starts immediately"]
    AssignUrgent --> UpdateAllInterfaces["Update All Interfaces:<br>- FST dashboard<br>- Manager dashboard<br>- Technician interface<br>- Database sync<br>- Notifications sent"]
    QueueUrgent --> UpdateAllInterfaces
    QuickAssign --> UpdateAllInterfaces
    StandardUpdate --> UpdateAllInterfaces
    FSTActions -- "View Real-Time" --> ViewDash["View Real-Time Dashboard:<br>Order statuses<br>Technician workload<br>Completion rates<br>Blocked orders alerts"]
    AddComment --> UpdateAllInterfaces
    ViewDash --> UpdateAllInterfaces
    UpdateAllInterfaces --> FSTInterface
    EndDay --> SaveDayState["Save Final Day State:<br>- All order statuses<br>- Completed count<br>- Pending orders<br>- Blocked orders<br>- Technician summaries<br>- Work efficiency per tech<br>- Workplace utilization<br>- Time tracking data<br>- Save to DATABASE"]
    SaveDayState --> GenerateGraphs["Generate Graphs &amp; Stats:<br>📊 Orders completed today<br>📈 Progress trends<br>⏱️ Time efficiency<br>👷 Tech performance<br>🏭 Workplace usage<br>🚫 Blocked orders analysis"]
    GenerateGraphs --> SaveDB["💾 DATABASE SAVE:<br>Daily schedule archived<br>All metrics stored<br>Historical data preserved<br>PostgreSQL tables updated"]
    SaveDB --> NextDay{"Next Day<br>OR<br>End of Week?"}
    NextDay -- Next Day --> Start
    NextDay -- End of Week --> WeeklyReport["Generate Weekly Report:<br>📊 Total orders: Received vs Completed<br>📈 Daily completion trends<br>👷 Technician efficiency rankings<br>🏭 Workplace utilization rates<br>🚫 Blocked orders: Count &amp; reasons<br>⏱️ Average time per order<br>📉 Bottleneck analysis<br>💡 Recommendations"]
    WeeklyReport --> End(["System Running:<br>Continuous Monitoring<br>Daily Cycles<br>Weekly Reports"])

    LoadPrevious@{ shape: rect}
    DisplayedShift@{ shape: rect}
    style Start fill:#e1f5e1
    style WeeklyPrep fill:#fff4e1
    style UploadOrders fill:#fff4e1
    style AddLateOrders fill:#ffe4b5
    style ProcessUpdates fill:#e1f0ff
    style CheckSplit fill:#ffe4b5
    style SplitProcess fill:#ffe4b5
    style UploadShift1 fill:#fff4e1
    style DisplayedShift fill:#87ceeb
    style ManageTechnicians fill:#dda0dd
    style FindReplacement fill:#ffa500
    style ReassignOrder fill:#ffa500
    style GenerateSchedule fill:#e1f0ff
    style DisplaySchedule fill:#e1f0ff
    style TechInterface fill:#87ceeb
    style StartOrder fill:#90ee90
    style StopOrder fill:#ffa500
    style BlockOrder fill:#ff6b6b,color:#fff
    style EndOrder fill:#91d18b
    style SaveState fill:#f0e1ff
    style FSTInterface fill:#dda0dd
    style UrgentProcess fill:#ff0000,color:#fff
    style ShowOptions fill:#ff6b6b,color:#fff
    style ManagerStop fill:#ff0000,color:#fff
    style SaveDayState fill:#f0e1ff
    style SaveDB fill:#4169e1,color:#fff
    style WeeklyReport fill:#e1ffe1
    style End fill:#e1f5e1