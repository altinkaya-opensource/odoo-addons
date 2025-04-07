# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models, _, tools
import itertools, json


class SurveyQuestion(models.Model):
    _inherit = "survey.question"
    """This inheritance adds Star Rating question type to survey module."""

    question_type = fields.Selection(
        selection_add=[("star_rating", "Star Rating")],
    )

    star_count = fields.Integer(
        string="Star Count",
        default=5,
        help="Number of stars to be displayed in the survey.",
    )

    def validate_star_rating(self, post, answer_tag):
        self.ensure_one()
        errors = {}
        answer = post[answer_tag].strip()
        # Empty answer to mandatory question
        if self.constr_mandatory and not answer:
            errors.update({answer_tag: self.constr_error_msg})
        # Checks if user input is a number
        if answer:
            try:
                floatanswer = float(answer)
            except ValueError:
                errors.update({answer_tag: _("This is not a number")})
        # Answer validation (if properly defined)
        if answer and self.validation_required:
            # Answer is not in the right range
            with tools.ignore(Exception):
                floatanswer = float(
                    answer
                )  # check that it is a float has been done hereunder
                if not (
                    self.validation_min_float_value
                    <= floatanswer
                    <= self.validation_max_float_value
                ):
                    errors.update({answer_tag: self.validation_error_msg})
        return errors
    
    def _prepare_statistics(self, user_input_lines):
        """ Compute statistical data for questions by counting number of vote per choice on basis of filter """
        super()._prepare_statistics(user_input_lines)
        all_questions_data = []
        for question in self:
            question_data = {'question': question, 'is_page': question.is_page}

            if question.is_page:
                all_questions_data.append(question_data)
                continue

            # fetch answer lines, separate comments from real answers
            all_lines = user_input_lines.filtered(lambda line: line.question_id == question)
            if question.question_type in ['simple_choice', 'multiple_choice', 'matrix']:
                answer_lines = all_lines.filtered(
                    lambda line:
                        line.answer_type == 'suggestion' or (
                        line.skipped and not line.answer_type) or (
                        line.answer_type == 'char_box' and question.comment_count_as_answer)
                    )
                comment_line_ids = all_lines.filtered(lambda line: line.answer_type == 'char_box')
            elif question.question_type == 'text_box':
                answer_lines = all_lines.filtered(lambda line: line.answer_type == 'text_box')
                comment_line_ids = all_lines.filtered(lambda line: line.answer_type == 'text_box')
            else:
                answer_lines = all_lines
                comment_line_ids = self.env['survey.user_input.line']
            skipped_lines = answer_lines.filtered(lambda line: line.skipped)
            done_lines = answer_lines - skipped_lines
            question_data.update(
                answer_line_ids=answer_lines,
                answer_line_done_ids=done_lines,
                answer_input_done_ids=done_lines.mapped('user_input_id'),
                answer_input_skipped_ids=skipped_lines.mapped('user_input_id'),
                comment_line_ids=comment_line_ids)
            question_data.update(question._get_stats_summary_data(answer_lines))

            # prepare table and graph data
            table_data, graph_data = question._get_stats_data(answer_lines)
            question_data['table_data'] = table_data
            question_data['graph_data'] = json.dumps(graph_data)

            all_questions_data.append(question_data)
        return all_questions_data
    
    def _get_stats_data(self, user_input_lines):
        if self.question_type == 'star_rating':
            return self._get_stats_graph_data_star(user_input_lines)
        return [line for line in user_input_lines], []
    
    def _get_stats_graph_data_star(self, user_input_lines):
        suggested_answers = []
        for question in self:
            all_lines = user_input_lines.filtered(lambda line: line.question_id == question)
            suggested_answers.extend(all_lines.filtered(lambda line: line.question_id.question_type == 'star_rating'))
        count_data = dict.fromkeys(['1.0','2.0','3.0','4.0','5.0'], 0)
        for answer in suggested_answers:
            if answer.answer_type == "numerical_box":
                count_data[answer.display_name] += 1
        total_count = sum(count_data.values())
        table_data = [
            {
                'value': value,
                'count': count,
                'value_text': _("%s Star") % value[0],
                'count_text': _("%s Votes") % count,
                'perc_data': _("%.2f%%") % (count / total_count * 100) if total_count > 0 else "0.00%",
            }
                for value, count in count_data.items()
        ]

        graph_data = [
            {'text': item['value_text'], 'count': item['count']}
            for item in table_data
        ]

        return table_data, graph_data
    
    