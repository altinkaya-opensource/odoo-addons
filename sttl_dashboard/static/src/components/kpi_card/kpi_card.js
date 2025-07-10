/** @odoo-module */

const { Component, onWillStart, useRef, onMounted,useState } = owl
import { useService } from "@web/core/utils/hooks";
export class KpiCard extends Component {

    setup(){
         super.setup();
         this.orm = useService("orm");
         this.action = useService("action");
         onWillStart(()=>{

            if(this.props.aggregate){
              this.props.aggregate = this.formatPrice(this.props.aggregate)
            }
         })
    }
    formatPrice(price) {
          if (price < 1000) {
            return price.toString();
          } else if (price < 100000) {
            return (price / 1000).toFixed(1) + "K";
          } else {
            return (price / 10000000).toFixed(1) + "Mn";
          }
    }
    redirectToModel(){
     if(this.props.model){
          this.action.doAction({
          type: 'ir.actions.act_window',
          name: this.props.model,
          res_model: this.props.model,
          views: [[false, 'tree']],
          target: 'current',
         });
     }
    }
    editKpi(){
        this.action.doAction({
          type: 'ir.actions.act_window',
          name: 'Kpi Generator',
          res_model: 'kpi.card.generator',
          res_id:this.props.id,
          views: [[false, 'form']],
          target: 'new',
         });
    }

     deleteKpi(){
       this.props.onDelete(this.props.count,this.props.type,this.props.id)
    }

}

KpiCard.template = "owl.KpiCard"
