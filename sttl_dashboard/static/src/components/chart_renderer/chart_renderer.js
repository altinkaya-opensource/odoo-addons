/** @odoo-module */

import { registry } from "@web/core/registry"
import { loadJS } from "@web/core/assets"
import { useService } from "@web/core/utils/hooks";
const { Component, onWillStart, useRef, onMounted } = owl

export class ChartRenderer extends Component {
    setup(){
        this.chartRef = useRef("chart")
        this.orm = useService("orm");
        this.action = useService("action");
        onWillStart(async ()=>{
            await loadJS("https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js")
        })

        onMounted(()=>this.renderChart())
    }

        deleteItem() {
            if (this.props.onDelete) {
              this.props.onDelete(this.props.config.count,this.props.config.type,this.props.config.id)
            }
        }
    async deleteChart(){
     let text = "Are you sure to delete this chart!\nEither OK or Cancel.";
     if (confirm(text) == true) {
         try{
           await this.orm.unlink('chart.generator', [this.props.config.id]);
           window.location.reload();
         }
         catch(e){
          console.log('error occured')
         }
    } else {
        console.log('cancelled')
    }
   }

   editChart(){
    this.action.doAction({
      type: 'ir.actions.act_window',
      name: 'Chart Generator',
      res_model: 'chart.generator',
      res_id:this.props.config.id,
      views: [[false, 'form']],
      target: 'new',
     });
    }

renderChart() {
    new Chart(this.chartRef.el, {
        type: this.props.type,
        data: this.props.config,
        options: {
            onClick: async (e, activeElements) => {
                if (activeElements.length > 0) {
                    const fieldLabel = this.props.config.labels[activeElements[0].index];

                    const modelName = this.props.config.model_name;
                    const fieldName = this.props.config.field_name;
                          try{
                             this.action.doAction({
                             type: 'ir.actions.act_window',
                             name: 'Chart Generator',
                             res_model: modelName,
                                  context: {
                                        'group_by': fieldName,
                                    },
                             domain: [[fieldName, '=', fieldLabel]],
                             views: [[false, 'list'],[false, 'form']],
                             target: 'new',
                                     });
                          }
                          catch(e){
                           console.log('error occured')
                          }
                } else {
                    console.log('Clicked outside of a data point');
                }
            },
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom',
                },
                title: {
                    display: true,
                    text: this.props.title,
                    position: 'bottom',
                }
            }
        },
    });
}

}

ChartRenderer.template = "owl.ChartRenderer"