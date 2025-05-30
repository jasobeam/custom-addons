# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal

class ContractsController(http.Controller):
    """Handles listing and displaying subscription contracts in the portal"""

    @http.route(['/my/contracts'], type='http', auth='user', website=True)
    def portal_contracts_list(self, **kwargs):
        # Fetch current user and apply domain
        user = request.env.user
        domain = []
        if not user.has_group('base.group_system'):
            domain = [
                ('partner_id', '=', user.partner_id.id)
            ]
        records = request.env['subscription.contracts'].sudo().search(domain)
        # Render the contracts list template
        return request.render('sales_contract_and_recurring_invoices.tmp_contract_details', {
            'records': records
        })

    @http.route(['/my/contracts/<int:contract_id>'], type='http', auth='user', website=True)
    def portal_contract_details(self, contract_id, **kwargs):
        # Browse the contract record (sudo to avoid access restrictions)
        record = request.env['subscription.contracts'].sudo().browse(contract_id)
        # Ensure record belongs to the user unless admin
        if not request.env.user.has_group('base.group_system') and record.partner_id != request.env.user.partner_id:
            return request.redirect('/my')
        return request.render('sales_contract_and_recurring_invoices.contract_details', {
            'record': record
        })

    @http.route(['/my/contracts/<int:contract_id>/print'], type='http', auth='user', website=True)
    def portal_contract_print(self, contract_id, **kwargs):
        # Print PDF report for the contract
        report_ref = 'sales_contract_and_recurring_invoices.action_report_subscription_contracts'
        report_action = request.env.ref(report_ref)
        pdf_content, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(report_action.report_name, [
            contract_id
        ])
        # Return PDF response
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf_content)),
        ]
        return request.make_response(pdf_content, headers=headers)
