"""Promotion management boundaries; SQL lifecycle/concurrency is tested separately."""
import unittest
from unittest.mock import MagicMock
from app.services import ambassador_promotions as promo
from app.services.ambassador_service import AmbassadorError

class PromoManagementTests(unittest.TestCase):
    def db(self, campus='a'):
        db=MagicMock();q=db.table.return_value
        q.select.return_value=q;q.eq.return_value=q;q.single.return_value=q
        q.execute.return_value={'id':'message','profile_id':'student','campus_id':campus}
        db.rpc.return_value={'message':{'id':'message','revision':2}}
        return db

    def test_scope_checked_before_edit_or_delete_rpc(self):
        for action in ['edit','delete']:
            db=self.db('foreign')
            with self.assertRaises(AmbassadorError) as error:
                promo.manage(db,'actor','message','a',1,action,{'caption':'Hello {{link}}'})
            self.assertEqual(error.exception.status,403);db.rpc.assert_not_called()

    def test_revision_required_and_not_boolean(self):
        for revision in [None,True,0,-1,'1']:
            db=self.db()
            with self.assertRaises(AmbassadorError):promo.manage(db,'actor','message','a',revision,'delete')
            db.rpc.assert_not_called()

    def test_edit_cannot_change_targets_month_or_other_fields(self):
        db=self.db()
        with self.assertRaises(AmbassadorError):promo.manage(db,'actor','message','a',1,'edit',{'target_all':True})
        db.rpc.assert_not_called()

    def test_edit_does_not_create_or_reassign_recipients(self):
        db=self.db();promo.manage(db,'actor','message','a',1,'edit',{'caption':' New {{link}} ','image_url':None,'revision':1})
        db.rpc.assert_called_once_with('hg_manage_ambassador_promo',{'p_actor':'actor','p_id':'message','p_revision':1,'p_action':'edit','p_values':{'caption':'New {{link}}','image_url':None}})

    def test_contact_uses_separate_rpc_and_normalises_local_number(self):
        db=self.db();db.rpc.return_value={'whatsapp_phone':'+2348012345678'}
        promo.contact(db,'actor','student','a','0801 234 5678')
        db.rpc.assert_called_once_with('hg_set_ambassador_whatsapp',{'p_actor':'actor','p_ambassador':'student','p_phone':'+2348012345678'})
        self.assertEqual(db.table.call_args.args,('ambassadors',))

    def test_contact_cannot_cross_selected_super_admin_scope(self):
        db=self.db('b')
        with self.assertRaises(AmbassadorError):promo.contact(db,'actor','student','a','+2348012345678')
        db.rpc.assert_not_called()

    def test_invalid_contact_and_remote_image_never_reach_rpc(self):
        for phone in ['javascript:alert(1)',True,'123',{},'+2348012345678\n']:
            with self.subTest(phone=phone):
                db=self.db()
                with self.assertRaises(AmbassadorError):promo.contact(db,'actor','student','a',phone)
                db.rpc.assert_not_called()
        for value in ['https://evil.test/a.jpg','https://res.cloudinary.com.evil.test/image/upload/a.jpg','http://res.cloudinary.com/test/image/upload/a.jpg']:
            with self.assertRaises(AmbassadorError):promo.image_url(value)

    def test_rpc_conflicts_and_forbidden_are_actionable(self):
        for name,status in [('promo_deleted',409),('promo_stale',409),('promo_forbidden',403)]:
            with self.assertRaises(AmbassadorError) as error:promo.result_or_error({'error':name})
            self.assertEqual(error.exception.status,status)
