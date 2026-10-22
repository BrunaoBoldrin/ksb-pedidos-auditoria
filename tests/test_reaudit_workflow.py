import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from order_workflow import (
    ReauditConfirmationRequired,
    approved_orders_in_batch,
    process_uploaded_orders,
    upload_fingerprints,
)


class ReauditWorkflowTests(unittest.TestCase):
    def files(self, *names):
        return [SimpleNamespace(name=name) for name in names]

    def processor(self, order_number):
        return (
            pd.DataFrame([{"Numero Pedido": order_number, "Item": "00010"}]),
            pd.DataFrame(
                [
                    {
                        "Pedido": order_number,
                        "Item": "00010",
                        "Status": "OK",
                        "Status Comercial": "OK",
                    }
                ]
            ),
        )

    def test_new_order_processes_without_reaudit_confirmation(self):
        process = Mock(side_effect=lambda name: self.processor("4501"))
        register = Mock(return_value=1)

        results = process_uploaded_orders(
            self.files("novo.pdf"),
            "Admin",
            [],
            (False, False),
            process,
            register,
        )

        self.assertEqual(len(results), 1)
        register.assert_called_once()
        self.assertFalse(register.call_args.kwargs["reavaliacao"])

    def test_approved_order_requires_both_confirmations(self):
        process = Mock()
        register = Mock()
        for confirmations in ((False, False), (True, False), (False, True)):
            with self.subTest(confirmations=confirmations):
                with self.assertRaises(ReauditConfirmationRequired):
                    process_uploaded_orders(
                        self.files("aprovado.pdf"),
                        "Admin",
                        ["4501"],
                        confirmations,
                        process,
                        register,
                    )
        process.assert_not_called()
        register.assert_not_called()

    def test_two_confirmations_release_reaudit_and_are_persisted(self):
        process = Mock(side_effect=lambda name: self.processor("4501"))
        register = Mock(return_value=1)

        process_uploaded_orders(
            self.files("aprovado.pdf"),
            "Admin",
            ["4501"],
            (True, True),
            process,
            register,
        )

        kwargs = register.call_args.kwargs
        self.assertTrue(kwargs["reavaliacao"])
        self.assertTrue(kwargs["confirmou_auditoria"])
        self.assertTrue(kwargs["confirmou_implantacao"])

    def test_mixed_batch_lists_every_previously_approved_order(self):
        mapping = {"novo.pdf": "4501", "aprovado-a.pdf": "4502", "aprovado-b.pdf": "4503"}
        approved = approved_orders_in_batch(
            self.files(*mapping),
            lambda name: mapping[name],
            lambda number: number in {"4502", "4503"},
        )
        self.assertEqual(approved, ["4502", "4503"])

    def test_each_pdf_is_persisted_independently(self):
        orders = iter(["4501", "4502"])
        process = Mock(side_effect=lambda name: self.processor(next(orders)))
        register = Mock(side_effect=[1, 2])

        results = process_uploaded_orders(
            self.files("a.pdf", "b.pdf"),
            "Admin",
            [],
            (False, False),
            process,
            register,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(register.call_count, 2)

    def test_mixed_batch_marks_only_previously_approved_order_as_reaudit(self):
        orders = iter(["4501", "4502"])
        process = Mock(side_effect=lambda name: self.processor(next(orders)))
        register = Mock(side_effect=[1, 2])

        process_uploaded_orders(
            self.files("novo.pdf", "aprovado.pdf"),
            "Admin",
            ["4502"],
            (True, True),
            process,
            register,
        )

        self.assertFalse(register.call_args_list[0].kwargs["reavaliacao"])
        self.assertTrue(register.call_args_list[1].kwargs["reavaliacao"])

    def test_persistence_failure_is_propagated_and_no_success_result_is_returned(self):
        process = Mock(side_effect=lambda name: self.processor("4501"))
        register = Mock(side_effect=RuntimeError("falha de banco"))

        with self.assertRaisesRegex(RuntimeError, "falha de banco"):
            process_uploaded_orders(
                self.files("a.pdf"),
                "Admin",
                [],
                (False, False),
                process,
                register,
            )

    def test_missing_order_number_is_not_persisted(self):
        process = Mock(side_effect=lambda name: self.processor(""))
        register = Mock()

        with self.assertRaisesRegex(ValueError, "Número do pedido não identificado"):
            process_uploaded_orders(
                self.files("sem-pedido.pdf"),
                "Admin",
                [],
                (False, False),
                process,
                register,
            )

        register.assert_not_called()

    def test_upload_fingerprint_changes_when_same_filename_has_new_content(self):
        first = SimpleNamespace(name="pedido.pdf", getvalue=lambda: b"pedido 4501")
        second = SimpleNamespace(name="pedido.pdf", getvalue=lambda: b"pedido 4502")

        self.assertNotEqual(upload_fingerprints([first]), upload_fingerprints([second]))


if __name__ == "__main__":
    unittest.main()
