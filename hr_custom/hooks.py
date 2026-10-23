app_name = "hr_custom"
app_title = "Hr Custom"
app_publisher = "akshayr11"
app_description = "app or custom hr features"
app_email = "akshay.r.ravi@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "hr_custom",
# 		"logo": "/assets/hr_custom/logo.png",
# 		"title": "Hr Custom",
# 		"route": "/hr_custom",
# 		"has_permission": "hr_custom.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/hr_custom/css/hr_custom.css"
# app_include_js = "/assets/hr_custom/js/hr_custom.js"

# include js, css files in header of web template
# web_include_css = "/assets/hr_custom/css/hr_custom.css"
# web_include_js = "/assets/hr_custom/js/hr_custom.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "hr_custom/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
doctype_js = {"Service Request": "public/js/service_request.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "hr_custom/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
	"methods": ["hr_custom.payslip.get_payslip_data"],
}

# Installation
# ------------

before_install = "hr_custom.setup.before_install"
after_install = "hr_custom.setup.after_install"
before_migrate = "hr_custom.setup.before_migrate"
after_migrate = "hr_custom.setup.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "hr_custom.uninstall.before_uninstall"
# after_uninstall = "hr_custom.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "hr_custom.utils.before_app_install"
# after_app_install = "hr_custom.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "hr_custom.utils.before_app_uninstall"
# after_app_uninstall = "hr_custom.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "hr_custom.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "hr_custom.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["hr_custom.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
	"Employee": {
		"validate": "hr_custom.utils.set_employee_category",
	},
	"Service Request": {
		"validate": "hr_custom.overrides.service_request.validate",
	},
	# transport documents: save who performed each workflow step
	**{
		doctype: {"validate": "hr_custom.overrides.workflow_users.set_workflow_users"}
		for doctype in ("Fleet Hiring Request", "Hiring Contract", "Equipment Timesheet", "Hiring Receipt")
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"hr_custom.tasks.all"
# 	],
# 	"daily": [
# 		"hr_custom.tasks.daily"
# 	],
# 	"hourly": [
# 		"hr_custom.tasks.hourly"
# 	],
# 	"weekly": [
# 		"hr_custom.tasks.weekly"
# 	],
# 	"monthly": [
# 		"hr_custom.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "hr_custom.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "hr_custom.custom.task.CustomTaskMixin"
# }
extend_doctype_class = {
	"Payroll Entry": "hr_custom.overrides.payroll_entry.PayrollEntryMixin",
	"Salary Structure Assignment": "hr_custom.overrides.salary_structure_assignment.SalaryStructureAssignmentMixin",
	"Salary Slip": "hr_custom.overrides.salary_structure_assignment.SalarySlipMixin",
}

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "hr_custom.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "hr_custom.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["hr_custom.utils.before_request"]
# after_request = ["hr_custom.utils.after_request"]

# Job Events
# ----------
# before_job = ["hr_custom.utils.before_job"]
# after_job = ["hr_custom.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"hr_custom.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

