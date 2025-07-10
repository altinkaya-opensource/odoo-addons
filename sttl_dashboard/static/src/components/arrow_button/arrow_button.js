/** @odoo-module */

import { registry } from "@web/core/registry"
import { loadJS } from "@web/core/assets"
import { useService } from "@web/core/utils/hooks";
const { Component, onWillStart, useRef, onMounted } = owl


export class ArrowButton extends Component {

 redirectToModel(){
   if(this.props.chartdata['model_name']){
      this.action.doAction({
      type: 'ir.actions.act_window',
      name: this.props.chartdata['model_name'],
      res_model: this.props.chartdata['model_name'],
      views: [[false, 'tree']],
      target: 'current',
     });
     }
 }
 setup(){
     this.orm = useService("orm");
     this.action = useService("action");
    }

}

ArrowButton.template = "owl.ArrowButton"